"""Файловый лог ~/.ihonor/ihonor.log (rotating)."""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH = os.path.expanduser("~/.ihonor/ihonor.log")


def setup_logging() -> logging.Logger:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logger = logging.getLogger("ihonor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    h = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)
    return logger
