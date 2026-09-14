import logging
import logging.handlers
import sys

from dikte import paths


def setup_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return
    fh = logging.handlers.RotatingFileHandler(
        paths.log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)
    if sys.stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter(fmt))
        root.addHandler(sh)
