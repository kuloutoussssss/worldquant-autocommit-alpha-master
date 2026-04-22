# -*- coding: utf-8 -*-
"""
同步串行批量回测脚本
简单直接，逐个提交和等待结果
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from pathlib import Path
from typing import Dict
from core.api_client import BrainAPIClient
from core.db_manager import get_database
from core.logger import logger


class SyncBatchBacktester:
    """同步串行回测器 - 简单直接"""
    
    def __init__(self, request_delay: float = 3.0):
        """
        初始化回测器
        
        Args:
            request_delay: 请求间隔（秒），避免过快被限流，默认3秒确保安全
        """
        self.client = BrainAPIClient()
        self.request_delay = request_delay
        self.db = get_database()
        
        # 统计
        self.total = 0
        self.completed = 0
        self.failed = 0
    
    def run(self, alpha_file: str, universe: str = "TOP3000",
            region: str = "USA", decay: int = 30,
            neutralization: str = "SECTOR",
            truncation: float = 0.08,
            test_period: str = "P2Y0M"):
        """运行批量回测（同步方式）"""
        print("=" * 60)
        print("同步串行批量回测")
        print("=" * 60)
        print(f"Alpha 文件: {alpha_file}")
        print(f"Universe: {universe}")
        print(f"Region: {region}")
        print(f"请求间隔: {self.request_delay}s")
        print("=" * 60)
        
        # 读取 Alpha
        alphas = self._load_alphas(alpha_file)
        self.total = len(alphas)
        
        if not alphas:
            print("没有找到 Alpha 表达式")
            return
        
        print(f"\n加载了 {len(alphas)} 个 Alpha")
        print(f"预计耗时: {len(alphas) * 12 / 60:.1f} 分钟")
        
        # 确保认证
        if not self.client.ensure_session():
            print("认证失败!")
            return
        
        start_time = time.time()
        
        for i, (idx, expression) in enumerate(alphas, 1):
            print(f"\n[{i}/{self.total}] 提交 Alpha #{idx}...")
            
            # 1. 提交回测
            result = self.client.test_alpha(
                expression=expression,
                universe=universe,
                region=region,
                decay=decay,
                neutralization=neutralization,
                truncation=truncation,
                test_period=test_period
            )
            
            if result.get("status") != "OK":
                self.failed += 1
                print(f"  提交失败: {result.get('error', 'Unknown')[:50]}")
                time.sleep(self.request_delay)
                continue
            
            location = result.get("location", "")
            print(f"  提交成功，等待结果...")
            
            # 2. 等待结果
            result = self.client.get_simulation_result(location)
            
            if result.get("status") == "OK":
                self._save_result(idx, expression, location, result)
                self.completed += 1
            else:
                self.failed += 1
                print(f"  回测失败: {result.get('error', 'Unknown')[:50]}")
            
            # 请求间隔
            if i < self.total:
                time.sleep(self.request_delay)
        
        # 统计
        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print("回测完成!")
        print("=" * 60)
        print(f"总数:     {self.total}")
        print(f"成功:     {self.completed}")
        print(f"失败:     {self.failed}")
        print(f"成功率:   {self.completed/max(1,self.total)*100:.1f}%")
        print(f"总耗时:   {total_time/60:.1f} 分钟")
        print("=" * 60)
    
    def _load_alphas(self, alpha_file: str):
        """加载 Alpha 表达式"""
        alphas = []
        path = Path(alpha_file)
        
        if not path.exists():
            path = Path(__file__).parent.parent / alpha_file
        
        if not path.exists():
            logger.error(f"文件不存在: {alpha_file}")
            return []
        
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    alphas.append((idx, line))
        
        return alphas
    
    def _save_result(self, idx: int, expression: str, location: str, result: Dict):
        """保存回测结果"""
        try:
            data = result.get("data", {})
            info = data.get("info", {})
            is_data = data.get("is", {})
            
            alpha_id = location.split("/")[-1] if "/" in location else ""
            
            self.db.add_tested_expression(
                expression=expression,
                alpha_id=alpha_id,
                sharpe=is_data.get("sharpe"),
                fitness=is_data.get("fitness"),
                turnover=is_data.get("turnover"),
                returns=is_data.get("returns"),
                drawdown=is_data.get("drawdown"),
                status="OK"
            )
            
            sharpe = is_data.get("sharpe", 0)
            print(f"  完成! Sharpe: {sharpe:.3f}")
            
        except Exception as e:
            logger.error(f"保存结果失败: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="同步串行批量回测")
    parser.add_argument("-f", "--file", default="data/alphas/to_test.txt",
                       help="Alpha 表达式文件路径")
    parser.add_argument("-u", "--universe", default="TOP3000",
                       help="Universe (默认: TOP3000)")
    parser.add_argument("-r", "--region", default="USA",
                       help="Region (默认: USA)")
    parser.add_argument("-d", "--decay", type=int, default=30,
                       help="Decay (默认: 30)")
    parser.add_argument("-delay", type=float, default=1.0,
                       help="请求间隔秒数 (默认: 1.0)")
    
    args = parser.parse_args()
    
    tester = SyncBatchBacktester(request_delay=args.delay)
    tester.run(
        alpha_file=args.file,
        universe=args.universe,
        region=args.region,
        decay=args.decay
    )
