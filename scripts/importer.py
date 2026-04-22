# -*- coding: utf-8 -*-
"""从 alpha-tools 结果导入合格 Alpha"""
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from core.logger import logger
from core.filter import filter_qualified_alpha_ids

# 默认路径
DEFAULT_ALPHA_TOOLS_PATH = "alpha-tools"
DEFAULT_OUTPUT = "data/alphas/alpha_ids.txt"


def import_from_alpha_tools(alpha_tools_path: str = DEFAULT_ALPHA_TOOLS_PATH,
                           candidate_alpha_id_file: str = DEFAULT_OUTPUT) -> List[str]:
    """
    从 alpha-tools 结果目录导入合格 Alpha ID
    
    Args:
        alpha_tools_path: alpha-tools 结果目录
        candidate_alpha_id_file: 保存候选 Alpha ID 的文件
    
    Returns:
        合格 Alpha ID 列表
    """
    path = Path(alpha_tools_path)
    
    if not path.exists():
        logger.error(f"Directory not found: {alpha_tools_path}")
        return []
    
    # 文件路径
    qualified_file = path / "qualified_alphas.json"
    all_results_file = path / "all_results.json"
    valid_alpha_ids = []
    
    try:
        # 优先读取达标文件（已经是6项全部PASS）
        if qualified_file.exists():
            logger.info(f"Reading qualified file: {qualified_file}")
            with open(qualified_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                valid_alpha_ids = data
            elif isinstance(data, dict) and 'alpha_ids' in data:
                valid_alpha_ids = data['alpha_ids']
            
            logger.info(f"Loaded {len(valid_alpha_ids)} qualified alphas from qualified file")
        # 从全量结果中筛选
        elif all_results_file.exists():
            logger.info(f"Reading results file: {all_results_file}")
            with open(all_results_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            valid_alpha_ids = filter_qualified_alpha_ids(data, key='results')
            logger.info(f"Filtered {len(valid_alpha_ids)} qualified alphas from {data.get('total', 0)} total")
        else:
            logger.error(f"No result files found in {alpha_tools_path}")
            logger.info(f"Please check if alpha-tools has completed")
            return []
        
        # 保存到文件
        if valid_alpha_ids:
            Path(candidate_alpha_id_file).parent.mkdir(parents=True, exist_ok=True)
            with open(candidate_alpha_id_file, 'w', encoding='utf-8') as f:
                for aid in valid_alpha_ids:
                    f.write(f"{aid}\n")
            
            logger.info(f"Saved to: {candidate_alpha_id_file}")
        else:
            logger.warning("No qualified alphas found")
        
        return valid_alpha_ids
    
    except FileNotFoundError:
        logger.error(f"Directory not found: {alpha_tools_path}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
    except Exception as e:
        logger.error(f"Error: {e}")
    
    return []


def get_qualified_count(alpha_tools_path: str = DEFAULT_ALPHA_TOOLS_PATH) -> Tuple[int, int]:
    """获取合格 Alpha 数量"""
    path = Path(alpha_tools_path)
    qualified_file = path / "qualified_alphas.json"
    all_results_file = path / "all_results.json"
    
    if qualified_file.exists():
        with open(qualified_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data), 0
        elif isinstance(data, dict) and 'alpha_ids' in data:
            return len(data['alpha_ids']), 0
    
    if all_results_file.exists():
        with open(all_results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        qualified = filter_qualified_alpha_ids(data, key='results')
        return len(qualified), data.get('total', 0)
    
    return 0, 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import qualified alphas from alpha-tools")
    parser.add_argument("--path", default=DEFAULT_ALPHA_TOOLS_PATH, help="alpha-tools path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output file")
    args = parser.parse_args()
    
    ids = import_from_alpha_tools(args.path, args.output)
    print(f"\nImported {len(ids)} qualified alphas")
