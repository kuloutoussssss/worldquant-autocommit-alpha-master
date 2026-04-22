# -*- coding: utf-8 -*-
"""
Web 工具函数
提供 Alpha 列表管理、文件操作等辅助函数
"""
from pathlib import Path
from core.db_manager import get_database


def get_data_dir():
    """获取数据目录"""
    return Path(__file__).parent.parent.parent / "data" / "alphas"


def get_to_test_path():
    """获取 to_test.txt 路径"""
    return get_data_dir() / "to_test.txt"


def load_to_test_alphas():
    """加载待回测的 Alpha 列表"""
    path = get_to_test_path()
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def save_to_test_alphas(alphas):
    """保存待回测的 Alpha 列表"""
    path = get_to_test_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for alpha in alphas:
            f.write(alpha + "\n")


def cleanup_tested_from_file():
    """从 to_test.txt 删除已回测的表达式"""
    db = get_db()
    tested_exprs = db.get_tested_expressions()
    
    alphas = load_to_test_alphas()
    original_count = len(alphas)
    
    remaining = []
    removed = 0
    for alpha in alphas:
        expr = alpha.split("|")[0].strip()
        if expr not in tested_exprs:
            remaining.append(alpha)
        else:
            removed += 1
    
    save_to_test_alphas(remaining)
    
    return original_count, removed, len(remaining)


def get_db():
    """获取数据库实例"""
    return get_database()
