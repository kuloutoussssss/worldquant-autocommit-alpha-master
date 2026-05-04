# -*- coding: utf-8 -*-
"""
WorldQuant Brain Alpha 自动化系统 - 主程序入口
"""

import os
import sys
from pathlib import Path

# 加载.env文件
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# 设置控制台编码为UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from core.batch_tester import AlphaBatchTester
from core.submit import submit_alpha_ids, THROTTLE_ERRORS, NETWORK_ERRORS
from scripts.workflow import run_full_workflow
from core.api_client import BrainAPIClient
from core.db_manager import get_database
from scripts.factor_builder import build_factor_pipeline, save_factors_for_batch_test
from core.neutralization_tester import NeutralizationTester, get_neutralization_options

# 统一文件路径
ALPHA_ID_PATH = "data/alphas/alpha_ids.txt"  # 待回测的Alpha ID列表
LATEST_CSV_PATH = "data/results/latest_extracted.csv"  # 最新的提取结果
os.makedirs(os.path.dirname(LATEST_CSV_PATH), exist_ok=True)
os.makedirs(os.path.dirname(ALPHA_ID_PATH), exist_ok=True)


def incremental_sync():
    """增量同步 - 从上次同步时间点获取更新的 Alpha"""
    db = get_database()
    client = BrainAPIClient()
    
    print("\n" + "=" * 50)
    print("增量同步")
    print("=" * 50)
    
    try:
        last_sync = db.get_last_sync_time()
        if last_sync:
            print(f"同步自 {last_sync.strftime('%Y-%m-%d %H:%M')} 以来的数据...")
            alphas = client.get_updated_alphas(
                since=last_sync,
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
            
            if alphas:
                new_count, update_count = db.save_alphas(alphas)
                print(f"新增 {new_count} 个, 更新 {update_count} 个")
            else:
                print("没有新增或更新的 Alpha")
        else:
            print("没有同步记录，将执行全量同步...")
            alphas = client.get_all_user_alphas(
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
            if alphas:
                new_count, update_count = db.save_alphas(alphas, is_full_sync=True)
                print(f"全量同步完成, 共 {new_count + update_count} 个 Alpha")
        
        db.print_report()
        # 自动更新候选池
        db.update_candidate_pool()
        db.print_candidate_pool()
    finally:
        client.session.close()


def submit_from_db(num_to_submit: int = None):
    """
    从候选池提交 Alpha（基于 8 项 Checks 验证）
    逻辑：直到成功达到目标数量才停止
    """
    from core.submit import THROTTLE_ERRORS
    
    db = get_database()
    client = BrainAPIClient()
    
    print("\n" + "=" * 50)
    print("提交 Alpha")
    print("=" * 50)
    
    candidates, total = db.get_candidates()
    
    if not candidates:
        print("没有符合条件可提交的 Alpha（需通过全部 8 项 Checks）")
        print("提示：请先执行增量/全量同步更新候选池")
        db.print_report()
        return
    
    print(f"找到 {len(candidates)} 个可提交的 Alpha")
    
    # 如果未指定数量，询问用户（目标成功数）
    if num_to_submit is None:
        num_to_submit = int(input(f"\n请输入目标成功数量 (1-{len(candidates)}, default 2): ").strip() or "2")
    num_to_submit = min(num_to_submit, len(candidates))
    
    print(f"目标: 成功提交 {num_to_submit} 个")
    
    successful = []
    failed = []
    skipped_429 = []
    
    for i, alpha in enumerate(candidates, 1):
        # 达到目标成功数后停止
        if len(successful) >= num_to_submit:
            print(f"\n✓ 目标达成 ({len(successful)} 个成功)，停止提交")
            break
        
        alpha_id = alpha['alpha_id']
        print(f"\n[{i}/{len(candidates)}] 提交: {alpha_id} (成功: {len(successful)}/{num_to_submit})")
        
        result = client.submit_alpha(alpha_id)
        
        if result and result.get('status') == 'OK':
            print(f"  ✓ 成功!")
            successful.append(alpha_id)
            db.mark_submitted(alpha_id)
        else:
            error = result.get('error', 'Unknown error') if result else 'No response'
            is_429 = any(t in str(error) for t in THROTTLE_ERRORS)
            is_network_error = any(t in str(error) for t in NETWORK_ERRORS)
            
            if is_429:
                print(f"  ⚠ 429 限流: {error}")
                skipped_429.append(alpha_id)
            elif is_network_error:
                print(f"  ⚠ 网络错误 (不计入失败): {error}")
                skipped_429.append(alpha_id)
            else:
                print(f"  ✗ 失败: {error}")
                failed.append(alpha_id)
                should_remove = db.mark_submit_failed(alpha_id, error)
                if not should_remove:
                    print(f"  {alpha_id} 已从候选池移除 (3次失败)")
        
        # 请求间隔
        if i < len(candidates) and len(successful) < num_to_submit:
            import time
            time.sleep(1)
    
    client.session.close()
    
    print(f"\n提交完成: {len(successful)} 成功, {len(failed)} 失败, {len(skipped_429)} 429限流")
    db.print_candidate_pool()


def auto_sync_and_submit(num_to_submit: int = 10):
    """
    全自动同步和提交流程

    筛选逻辑: 基于WorldQuant Brain官方8项checks验证结果
    """
    db = get_database()
    client = BrainAPIClient()
    
    print("\n" + "=" * 50)
    print("全自动同步 & 提交")
    print("=" * 50)

    try:
        # 1. 同步数据
        print("\n[1/3] 数据同步中...")
        last_sync = db.get_last_sync_time()

        if not db.has_data():
            print("   首次运行,执行全量同步...")
            alphas = client.get_all_user_alphas(
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
            db.save_alphas(alphas, is_full_sync=True)
        else:
            if last_sync:
                print(f"   增量同步,自 {last_sync.strftime('%Y-%m-%d %H:%M')} 以来...")
                alphas = client.get_updated_alphas(
                    since=last_sync,
                    min_sharpe=-999,
                    min_fitness=-999,
                    max_turnover=1e9
                )

                if alphas:
                    new_count, update_count = db.save_alphas(alphas)
                    if new_count == 0 and update_count == 0:
                        print("   没有新增或更新的 Alpha")
                    else:
                        print(f"   新增 {new_count} 个,更新 {update_count} 个")
                else:
                    print("   没有新增或更新的 Alpha")
            else:
                print("   执行全量同步...")
                alphas = client.get_all_user_alphas(
                    min_sharpe=-999,
                    min_fitness=-999,
                    max_turnover=1e9
                )

                if alphas:
                    new_count, update_count = db.save_alphas(alphas)
                    if new_count == 0 and update_count == 0:
                        print("   没有新增或更新的 Alpha")
                    else:
                        print(f"   新增 {new_count} 个,更新 {update_count} 个")
                    db.print_report()

        # 2. 检查可提交
        print("\n[2/3] 检查可提交的 Alpha (基于8项Checks验证)...")
        submittable = db.get_submittable_alphas(exclude_today_submitted=True)

        if not submittable:
            print("   没有符合条件可提交的 Alpha")
            db.print_report()
            return

        print(f"   找到 {len(submittable)} 个可提交的 Alpha")

        for i, alpha in enumerate(submittable[:min(10, num_to_submit)], 1):
            print(f"     {i}. {alpha['alpha_id']}: 夏普率={alpha['sharpe']:.2f}, "
                  f"适应度={alpha['fitness']:.2f}, 换手率={alpha['turnover']*100:.1f}%")

        with open(ALPHA_ID_PATH, 'w', encoding='utf-8') as f:
            for alpha in submittable[:num_to_submit]:
                f.write(alpha['alpha_id'] + '\n')

        print(f"   已保存 {min(num_to_submit, len(submittable))} 个到 {ALPHA_ID_PATH}")

        # 3. 提交
        print(f"\n[3/3] 提交 Alpha (最多 {num_to_submit} 个)...")
        submit_alpha_ids(ALPHA_ID_PATH, num_to_submit=num_to_submit)

        db.print_report()
        # 自动更新候选池
        db.update_candidate_pool()
        db.print_candidate_pool()
    finally:
        client.session.close()


def main():
    """主程序入口"""
    print("WorldQuant Brain Alpha 自动化系统")

    while True:
        print("\n" + "=" * 50)
        print("请选择操作:")
        print("=" * 50)
        print("1: 增量同步 (从上次同步时间获取更新)")
        print("2: 强制全量同步 (重新获取所有数据)")
        print("3: 提交 Alpha (从数据库，按8项Checks筛选)")
        print("4: 查看数据库状态")
        print("5: 构建Alpha因子 (从数据集生成)")
        print("6: 批量回测 Alpha (从 data/alphas/to_test.txt)")
        print("7: 回测 -> 筛选 -> 提交 (一键完成)")
        print("8: 启动 Web 前端")
        print("9: 中性化组合测试 (测试所有中性化×maxTrade)")
        print("-" * 50)
        print("0: 退出系统")
        print("-" * 50)

        try:
            choice = input("\n请选择操作 (0-9): ").strip()
            if choice == '0':
                print("再见!")
                break
            choice = int(choice)
        except ValueError:
            print("无效的输入,请输入 0-9 之间的数字")
            continue

        print()

        db = get_database()

        if choice == 8:
            # 启动 API 服务器和 Web 前端
            import subprocess
            import sys
            import threading
            import time
            
            # 检查端口是否被占用
            import socket
            def is_port_in_use(port):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    return s.connect_ex(('localhost', port)) == 0
            
            # 启动 API 服务器
            if not is_port_in_use(5000):
                print("启动 API 服务器...")
                api_proc = subprocess.Popen(
                    [sys.executable, "-m", "web.api_server"],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )
                time.sleep(2)
                print("✅ API 服务器已启动: http://localhost:5000")
            else:
                print("✅ API 服务器已在运行: http://localhost:5000")
            
            # 启动 Streamlit 前端
            print("启动 Web 前端...")
            print("前端地址: http://localhost:8501")
            print("API 地址: http://localhost:5000")
            print("按 Ctrl+C 停止前端")
            
            try:
                python_exe = sys.executable
                subprocess.run(
                    [python_exe, "-m", "streamlit", "run", "web/app.py", 
                     "--server.port", "8501", "--server.headless", "true"],
                    cwd=os.path.dirname(os.path.abspath(__file__))
                )
            except KeyboardInterrupt:
                print("\n前端已停止")

        elif choice == 1:
            # 增量同步
            incremental_sync()

        elif choice == 2:
            # 强制全量同步
            print("警告: 这将重新获取所有 Alpha 数据（包括负收益的）")
            confirm = input("确认执行? (y/N): ").strip().lower()
            if confirm == 'y':
                client = BrainAPIClient()
                print("执行全量同步...")
                try:
                    alphas = client.get_all_user_alphas(
                        min_sharpe=-999,
                        min_fitness=-999,
                        max_turnover=1e9
                    )
                    print(f"获取了 {len(alphas)} 个 Alpha")
                    db.save_alphas(alphas, is_full_sync=True)
                    db.print_report()
                    # 自动更新候选池
                    db.update_candidate_pool()
                    db.print_candidate_pool()
                finally:
                    client.session.close()

        elif choice == 3:
            # 提交 Alpha - 使用候选池
            db.print_candidate_pool()
            candidates, total = db.get_candidates()
            
            if not candidates:
                print("\n没有可提交的Alpha，请先执行增量/全量同步")
            else:
                print(f"\n可选候选: {len(candidates)}")
                num = input(f"请输入要提交的数量 (1-{len(candidates)}, 默认1): ").strip()
                num = int(num) if num else 1
                num = max(1, min(num, len(candidates)))
                
                submit_from_db(num_to_submit=num)

        elif choice == 4:
            db.print_report()

        elif choice == 5:
            print("\n" + "=" * 50)
            print("构建Alpha因子")
            print("=" * 50)
            dataset_id = input("数据集ID (default fundamental6): ").strip() or "fundamental6"
            max_factors = int(input("构建因子数量 (default 10): ").strip() or "10")

            append_input = input("追加到现有文件 (y/n, default n): ").strip().lower()
            append_mode = append_input in ('y', 'yes')

            existing_count = 0
            if append_mode and os.path.exists('data/alphas/to_test.txt'):
                with open('data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
                    existing_count = len([line for line in f if line.strip()])
                print(f"现有文件包含 {existing_count} 个Alpha,将追加 {max_factors} 个")

            client = BrainAPIClient()
            result = build_factor_pipeline(
                client=client,
                dataset_id=dataset_id,
                max_factors=max_factors
            )
            client.session.close()

            if result['success']:
                save_factors_for_batch_test(
                    result['factors'],
                    'data/alphas/to_test.txt',
                    append=append_mode
                )
                total = existing_count + len(result['factors'])
                print(f"\n成功构建 {len(result['factors'])} 个Alpha因子")
                print(f"文件现在共有 {total} 个Alpha")
                print(f"可选择选项6进行批量回测")
            else:
                print(f"\n构建失败: {result.get('error', '未知错误')}")

        elif choice == 6:
            tester = AlphaBatchTester()
            tester.run(delay=10)

        elif choice == 7:
            # 全自动模式 - 读取配置文件
            config_path = Path("data/config.json")
            if config_path.exists():
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)['workflow']
                print(f"\n全自动模式启动:")
                print(f"  提交数量: {config['num_to_submit']}")
                print(f"  回测间隔: {config['delay']}秒")
                print(f"  最小Sharpe: {config['min_sharpe']}")
                print(f"  最小Fitness: {config['min_fitness']}")
                print(f"  最大Turnover: {config['max_turnover']*100}%")
                run_full_workflow(
                    num_to_submit=config['num_to_submit'],
                    delay=config['delay'],
                    min_sharpe=config['min_sharpe'],
                    min_fitness=config['min_fitness'],
                    max_turnover=config['max_turnover'],
                    input_file=config.get('input_file', 'data/alphas/to_test.txt')
                )
            else:
                print("未找到配置文件 data/config.json")
                print("请先执行选项1/2同步后，使用选项3手动提交")

        elif choice == 9:
            # 中性化组合测试
            print("\n" + "=" * 50)
            print("中性化组合测试")
            print("=" * 50)
            print("测试所有中性化方式 × maxTrade (ON/OFF) 组合")
            print("\n优质Alpha筛选条件:")
            print("1. 换手率 <= 0.4, Sharpe >= 1.2, Margin >= 0.0009")
            print("2. 换手率 <= 0.4, Sharpe >= 1.5, Margin >= 0.001")
            print("3. 换手率 <= 0.6, Sharpe >= 2.0, Margin >= 0.0015")
            print("=" * 50)

            # 输入Alpha表达式
            alpha_id = input("\n请输入Alpha ID (用于获取表达式和打标签): ").strip()
            if not alpha_id:
                print("Alpha ID不能为空")
            else:
                # 获取Alpha信息
                client = BrainAPIClient()
                try:
                    alpha_info = client.get_alpha(alpha_id)
                    if not alpha_info:
                        print(f"无法获取Alpha {alpha_id} 的信息")
                    else:
                        expression = alpha_info.get('regular', {}).get('code', '')
                        region = alpha_info.get('settings', {}).get('region', 'USA')
                        universe = alpha_info.get('settings', {}).get('universe', 'TOP3000')
                        decay = int(alpha_info.get('settings', {}).get('decay', 30))
                        truncation = float(alpha_info.get('settings', {}).get('truncation', 0.08))

                        # 显示将测试的组合
                        netu_options = get_neutralization_options(region)
                        print(f"\n将测试 {len(netu_options)} 种中性化 × 2 种maxTrade = {len(netu_options) * 2} 个组合")
                        print(f"中性化方式: {', '.join(netu_options)}")
                        print(f"maxTrade: ON, OFF")

                        confirm = input("\n确认开始测试? (y/N): ").strip().lower()
                        if confirm == 'y':
                            def progress_callback(current, total, result):
                                status = "✓" if result.get('status') == 'OK' else "✗"
                                quality = "★" if result.get('is_quality') else " "
                                print(f"  [{current}/{total}] {status} {quality} "
                                      f"{result.get('neutralization')}/{result.get('max_trade')} "
                                      f"Sharpe={result.get('sharpe', 0):.3f}")

                            tester = NeutralizationTester(
                                expression=expression,
                                region=region,
                                universe=universe,
                                decay=decay,
                                truncation=truncation,
                                base_alpha_id=alpha_id,
                                progress_callback=progress_callback
                            )

                            results = tester.test_all_combinations()

                            # 显示结果摘要
                            summary = tester.get_summary()
                            print(f"\n{'=' * 50}")
                            print("测试结果摘要")
                            print(f"{'=' * 50}")
                            print(f"总组合数: {summary['total_combinations']}")
                            print(f"成功完成: {summary['completed']}")
                            print(f"优质Alpha: {summary['quality_count']}")
                            print(f"最佳Sharpe: {summary['best_sharpe']:.3f}")

                            if summary['quality_alphas']:
                                print(f"\n优质Alpha列表:")
                                for qa in summary['quality_alphas']:
                                    print(f"  - {qa['alpha_id'][:20]}... "
                                          f"{qa['neutralization']}/{qa['max_trade']} "
                                          f"Sharpe={qa['sharpe']:.3f}")
                        else:
                            print("已取消")

                except Exception as e:
                    print(f"获取Alpha信息失败: {e}")

        else:
            print("无效的选择,请输入 0-9 之间的数字")

        input("\n按回车键继续...")


if __name__ == "__main__":
    main()
