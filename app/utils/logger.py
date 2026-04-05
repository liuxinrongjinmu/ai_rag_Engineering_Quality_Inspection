"""
日志工具模块
使用loguru提供统一的日志记录
"""
import sys
from loguru import logger
from pathlib import Path


def setup_logger(log_dir: str = "./logs", debug: bool = False):
    """
    配置日志记录器
    
    :param log_dir: 日志目录
    :param debug: 是否开启调试模式
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    logger.remove()
    
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    logger.add(
        sys.stdout,
        format=log_format,
        level="DEBUG" if debug else "INFO",
        colorize=True
    )
    
    logger.add(
        log_path / "app_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        compression="zip"
    )
    
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="ERROR",
        rotation="00:00",
        retention="30 days"
    )
    
    return logger


def get_logger():
    """
    获取日志记录器
    """
    return logger
