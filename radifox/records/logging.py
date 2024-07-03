import datetime
import logging
from pathlib import Path
import sys


WARNING_DEBUG = 25


class LogFilter(logging.Filter):
    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.level


def create_loggers(
    log_dir: Path,
    log_prefix: str,
    verbose: bool = False,
    add_stream_handler: bool = True,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # noinspection PyTypeChecker
    log_file = logging.FileHandler(log_dir / f"{log_prefix}-{timestamp}-info.log", delay=True)
    log_file.setFormatter(log_formatter)
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger().addHandler(log_file)
    if add_stream_handler:
        log_stream = logging.StreamHandler(sys.stdout)
        log_stream.setFormatter(log_formatter)
        logging.getLogger().addHandler(log_stream)
    # noinspection PyTypeChecker
    warn_file = logging.FileHandler(log_dir / f"{log_prefix}-{timestamp}-warning.log", delay=True)
    warn_file.addFilter(LogFilter(logging.ERROR - 1))
    logging.addLevelName(WARNING_DEBUG, "WARNING-DEBUG")
    warn_file.setFormatter(log_formatter)
    warn_file.setLevel(WARNING_DEBUG if verbose else logging.WARNING)
    logging.getLogger().addHandler(warn_file)
    # noinspection PyTypeChecker
    error_file = logging.FileHandler(log_dir / f"{log_prefix}-{timestamp}-error.log", delay=True)
    error_file.addFilter(LogFilter(logging.ERROR))
    error_file.setFormatter(log_formatter)
    error_file.setLevel(logging.ERROR)
    logging.getLogger().addHandler(error_file)
