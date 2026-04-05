"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# Global limiter instance — uses Redis as storage so limits survive restarts
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
)
