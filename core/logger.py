# -*- coding: utf-8 -*-
"""
日志模块 - 统一日志系统

控制台:显示INFO及以上（简洁格式）
文件:记录DEBUG及以上（按日期分割）
"""

import logging
import os
from pathlib import Path
from datetime import datetime


def setup_logger(name='AlphaCommit', log_dir='logs', level=logging.DEBUG):
    """
    初始化日志系统
    - 控制台:显示INFO及以上
    - 文件:记录DEBUG及以上,按日期分割
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
            print(f"⚠️ 警告:无法创建日志目录 {log_dir}: {e}")

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    log_file = os.path.join(log_dir, f"alpha_commit_{datetime.now().strftime('%Y%m%d')}.log")
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except PermissionError:
        logger.warning(f"⚠️ 日志文件写入失败,仅输出到控制台: {log_file}")

    return logger


# 全局日志实例
logger = setup_logger()
