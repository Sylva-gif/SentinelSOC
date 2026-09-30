import json
import logging
from datetime import datetime, timezone

from app.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record):
        message = record.getMessage()
        try:
            payload = json.loads(message)
            if not isinstance(payload, dict):
                payload = {"message": message}
        except (ValueError, TypeError):
            payload = {"message": message}
        return json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                           "level": record.levelname, "service": settings.service_role,
                           "logger": record.name, **payload}, ensure_ascii=False)


def configure_logging():
    logger = logging.getLogger("sentinel")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
