import logging
import sys

from colorama import Fore, Style, init

init(autoreset=True)

_FMT = "%(message)s"


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        prefix = {
            logging.DEBUG: "[DEBUG]",
            logging.INFO: "[INFO] ",
            logging.WARNING: "[WARN] ",
            logging.ERROR: "[ERROR]",
            logging.CRITICAL: "[CRIT] ",
        }.get(record.levelno, "[LOG]  ")
        msg = super().format(record)
        return f"{color}{prefix}{Style.RESET_ALL} {msg}"


def get_logger(name: str = "socialposter") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ColorFormatter(_FMT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


logger = get_logger()
