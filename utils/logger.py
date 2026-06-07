"""Centralised logging setup."""
import logging
import logging.handlers
from pathlib import Path

from utils.config import get_config


def setup_logger(name: str = "eye_agent") -> logging.Logger:
    cfg = get_config()
    log_cfg = cfg.logging

    log_path = Path(log_cfg["file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_cfg["level"], logging.INFO))

    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=log_cfg["max_bytes"],
            backupCount=log_cfg["backup_count"],
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger


log = setup_logger()
