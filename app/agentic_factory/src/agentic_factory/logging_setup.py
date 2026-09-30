import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """The process's log: one line per record on stderr, with the time of day."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%H:%M:%S"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
