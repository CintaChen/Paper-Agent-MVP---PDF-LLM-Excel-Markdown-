"""日志配置"""
import logging
import sys
from config.settings import settings


def setup_logging(name: str = "scholarAgent") -> logging.Logger:
    """统一日志配置"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # 格式
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # 避免重复添加
    if not logger.handlers:
        logger.addHandler(console_handler)

    return logger
