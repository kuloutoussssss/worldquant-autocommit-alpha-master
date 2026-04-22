# -*- coding: utf-8 -*-
"""
异步批量回测命令行工具
用法: python async_batch_tester.py [--input FILE] [--output FILE] [--concurrency N] [--max-count N]
"""
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from core.batch_tester import run_async_batch


def main():
    parser = argparse.ArgumentParser(description='异步批量回测 Alpha')
    parser.add_argument('--input', '-i', default='data/alphas/to_test.txt',
                       help='输入文件路径 (默认: data/alphas/to_test.txt)')
    parser.add_argument('--output', '-o', default='data/results/batch_results.json',
                       help='输出文件路径 (默认: data/results/batch_results.json)')
    parser.add_argument('--concurrency', '-c', type=int, default=5,
                       help='并发数 (默认: 5)')
    parser.add_argument('--max-count', '-n', type=int, default=None,
                       help='最大测试数量 (默认: 全部)')
    
    args = parser.parse_args()
    
    print(f"=" * 60)
    print(f"异步批量回测工具")
    print(f"=" * 60)
    print(f"输入文件: {args.input}")
    print(f"输出文件: {args.output}")
    print(f"并发数: {args.concurrency}")
    print(f"最大数量: {args.max_count if args.max_count else '全部'}")
    print(f"=" * 60)
    
    run_async_batch(
        input_file=args.input,
        output_file=args.output,
        concurrency=args.concurrency,
        max_count=args.max_count
    )


if __name__ == "__main__":
    main()
