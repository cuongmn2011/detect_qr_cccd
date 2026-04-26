import os
import sys
import logging
import threading
from datetime import datetime


def get_log_dir():
    """Get .temp folder path, creates it if needed.

    For exe: cạnh file exe
    For .py: cạnh source files
    """
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    log_dir = os.path.join(base_dir, '.temp')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


class DailyTextHandler(logging.Handler):
    """Thread-safe file handler that rotates daily.

    Automatically switches to new file at midnight.
    Safe for concurrent writes from multiple threads.
    """

    def __init__(self, log_dir):
        super().__init__()
        self.log_dir = log_dir
        self._lock = threading.Lock()
        self._current_date = None
        self._file = None

    def _rotate_if_needed(self):
        """Check if date changed, rotate file if needed."""
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self._current_date:
            if self._file:
                self._file.close()

            path = os.path.join(self.log_dir, f'{today}.txt')
            self._file = open(path, 'a', encoding='utf-8')
            self._current_date = today

    def emit(self, record):
        """Write log record to file (thread-safe)."""
        with self._lock:
            try:
                self._rotate_if_needed()
                msg = self.format(record)
                self._file.write(msg + '\n')
                self._file.flush()
            except Exception:
                self.handleError(record)

    def close(self):
        """Close file on shutdown."""
        with self._lock:
            if self._file:
                self._file.close()
        super().close()


def setup_logging(level=logging.DEBUG):
    """Setup root logger with DailyTextHandler.

    Called once at application startup.
    Logs all messages from all loggers to .temp/YYYY-MM-DD.txt
    """
    log_dir = get_log_dir()

    # Remove existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Setup format: timestamp | logger_name | level | message
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d | %(name)-20s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Create and add DailyTextHandler
    file_handler = DailyTextHandler(log_dir)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root_logger.addHandler(file_handler)
    root_logger.setLevel(level)

    return file_handler


