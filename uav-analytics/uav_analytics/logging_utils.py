import logging
import os


def setup_logging(level: int = logging.INFO, log_path: str = "logs/app.log") -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    root.addHandler(ch)

    # File
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    root.addHandler(fh)

