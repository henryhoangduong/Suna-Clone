import json
import logging
import os
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from utils.config import EnvMode, config

request_id: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": request_id.get(),
            "thread_id": getattr(record, "thread_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        if record.exc_info:
            log_data["exception"] = {
                "type": str(record.exc_info[0].__name__),
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data)


def setup_logger(name: str = "agentpress") -> logging.Logger:

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.getcwd(), "logs")
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            print(f"Created log directory at: {log_dir}")
    except Exception as e:
        print(f"Error creating log directory: {e}")
        return logger

    # File handler with rotation
    try:
        log_file = os.path.join(
            log_dir, f'{name}_{datetime.now().strftime("%Y%m%d")}.log'
        )
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"  # 10MB
        )
        file_handler.setLevel(logging.DEBUG)

        # Create formatters
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # Add file handler to logger
        logger.addHandler(file_handler)
        print(f"Added file handler for: {log_file}")
    except Exception as e:
        print(f"Error setting up file handler: {e}")

    # Console handler - WARNING in production, DEBUG in other environments
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        if config.ENV_MODE == EnvMode.PRODUCTION:
            console_handler.setLevel(logging.WARNING)
        else:
            console_handler.setLevel(logging.DEBUG)

        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # Add console handler to logger
        logger.addHandler(console_handler)
        logger.info(f"Added console handler with level: {console_handler.level}")
        logger.info(f"Log file will be created at: {log_dir}")
    except Exception as e:
        print(f"Error setting up console handler: {e}")

    return logger


# Create default logger instance
logger = setup_logger()
