"""
结构化日志配置
所有日志输出 JSON 格式，方便后续接入 ELK / Loki / 任何日志系统
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """在每条日志里附加固定字段"""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        log_record["service"] = "funasr-api"
        log_record["level"] = record.levelname
        # 去掉冗余字段
        log_record.pop("color_message", None)


def setup_logging(log_level: str = "INFO", log_dir: str = "/app/logs"):
    """
    配置双输出日志:
    - stdout: JSON 格式（给 Docker 日志驱动 / Loki 收集）
    - 文件:   按天轮转，保留 30 天
    """
    os.makedirs(log_dir, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    formatter = CustomJsonFormatter(
        fmt="%(timestamp)s %(level)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # stdout handler（给 Docker / systemd 收集）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # 文件 handler（按天轮转）
    log_file = os.path.join(log_dir, "funasr-api.log")
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=int(os.getenv("LOG_RETENTION_DAYS", "30")),
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    file_handler.suffix = "%Y-%m-%d"

    # 根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # 压低三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("modelscope").setLevel(logging.WARNING)
    logging.getLogger("funasr").setLevel(logging.WARNING)

    return logging.getLogger("funasr.api")
