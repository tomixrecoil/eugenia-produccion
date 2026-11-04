"""Logging simple a consola + archivo."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# En Windows la consola suele ser cp1252 y rompe con emojis/tildes.
# Forzamos UTF-8 en stdout para que el log se vea bien.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except (AttributeError, ValueError):
    pass


def get_logger(name: str = "marketing_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(ROOT / "agent.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
