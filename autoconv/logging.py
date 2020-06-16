import logging
import os
import sys


WARNING_DEBUG = 25


class LogFilter(logging.Filter):

    def __init__(self, level):
        super().__init__()
        self.level = level

    def filter(self, record):
        return record.levelno <= self.level


def create_loggers(output_root, scan_dir, verbose=False):
    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    log_stream = logging.StreamHandler(sys.stdout)
    log_stream.setFormatter(log_formatter)
    log_file = logging.FileHandler(os.path.join(output_root, scan_dir, 'conversion.log'))
    log_file.setFormatter(log_formatter)
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger().addHandler(log_stream)
    logging.getLogger().addHandler(log_file)
    warn_file = logging.FileHandler(os.path.join(output_root, scan_dir, 'warnings.log'), delay=True)
    warn_file.addFilter(LogFilter(logging.ERROR - 1))
    logging.addLevelName(WARNING_DEBUG, 'WARNING-DEBUG')
    warn_file.setFormatter(log_formatter)
    warn_file.setLevel(WARNING_DEBUG if verbose else logging.WARNING)
    logging.getLogger().addHandler(warn_file)
    error_file = logging.FileHandler(os.path.join(output_root, scan_dir, 'errors.log'), delay=True)
    error_file.addFilter(LogFilter(logging.ERROR))
    error_file.setFormatter(log_formatter)
    error_file.setLevel(logging.ERROR)
    logging.getLogger().addHandler(error_file)
