"""Rate limiting dependency."""

import logging
from typing import Annotated, Final

from fastapi import Depends, Header, HTTPException, Request, status

from suas.api.dependencies import LimiterDep
from suas.config import Settings, get_settings

logger: Final[logging.Logger] = logging.getLogger(__name__)

_ANONYMOUS: Final[str] = "anonymous"


def _client_key(request: Request, api_key: str | None) -> str:
    """Return a stable identifier for the caller.

    Prefers the API key so a shared NAT egress does not throttle every client
    behind it together. Falls back to the peer address.
    """
    if api_key:
        return f"key:{api_key}"
    client = request.client
    if client is None:
        return _ANONYMOUS
    return f"ip:{client.host}"


async def enforce_rate_limit(
    request: Request,
    limiter: LimiterDep,
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Reject the request when the caller has exceeded its allowance."""
    if not settings.rate_limit_enabled:
        return
    key: str = _client_key(request, x_api_key)
    if limiter.check(key):
        return
    retry_after: int = limiter.retry_after_s(key)
    logger.warning("Rate limit exceeded for %s", key)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )
