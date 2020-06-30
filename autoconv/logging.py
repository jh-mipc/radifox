import logging
from pathlib import Path
import sys

from .utils import mkdir_p


WARNING_DEBUG = 25


class LogFilter(logging.Filter):

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.level


def create_loggers(output_root: Path, scan_dir: Path, verbose: bool = False) -> None:
    mkdir_p(Path(output_root, scan_dir, 'logs'))
    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    log_stream = logging.StreamHandler(sys.stdout)
    log_stream.setFormatter(log_formatter)
    log_file = logging.FileHandler(Path(output_root, scan_dir, 'logs', 'conversion-info.log'), delay=True)
    log_file.setFormatter(log_formatter)
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger().addHandler(log_stream)
    logging.getLogger().addHandler(log_file)
    warn_file = logging.FileHandler(Path(output_root, scan_dir, 'logs', 'conversion-warnings.log'), delay=True)
    warn_file.addFilter(LogFilter(logging.ERROR - 1))
    logging.addLevelName(WARNING_DEBUG, 'WARNING-DEBUG')
    warn_file.setFormatter(log_formatter)
    warn_file.setLevel(WARNING_DEBUG if verbose else logging.WARNING)
    logging.getLogger().addHandler(warn_file)
    error_file = logging.FileHandler(Path(output_root, scan_dir, 'logs', 'conversion-errors.log'), delay=True)
    error_file.addFilter(LogFilter(logging.ERROR))
    error_file.setFormatter(log_formatter)
    error_file.setLevel(logging.ERROR)
    logging.getLogger().addHandler(error_file)
