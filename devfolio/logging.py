import json
import logging
import sys


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        result = {"level": record.levelname, "event": record.msg, "logger": record.name}
        for key in ("duration_ms", "request_id", "completed", "error_type"):
            if hasattr(record, key):
                result[key] = getattr(record, key)
        return json.dumps(result)


def configure_logging():
    logger = logging.getLogger("devfolio")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(SafeJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
