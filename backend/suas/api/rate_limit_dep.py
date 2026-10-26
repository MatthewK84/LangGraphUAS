"""Rate limiting dependency."""

import logging
from typing import Annotated, Final

from fastapi import Header, HTTPException, Request, status

from suas.api.dependencies import LimiterDep
from suas.api.security import SESSION_KEY_PREFIX

logger: Final[logging.Logger] = logging.getLogger(__name__)

_ANONYMOUS: Final[str] = "anonymous"
# Every browser session shares one bucket, as every browser shared the proxy's
# one key before #82: a fresh cookie must not buy a fresh allowance.
_SESSIONS: Final[str] = "sessions"


def _client_key(request: Request, api_key: str | None) -> str:
    """Return a stable identifier for the caller.

    Prefers the API key so a shared NAT egress does not throttle every client
    behind it together. Falls back to the peer address.
    """
    if api_key and api_key.startswith(SESSION_KEY_PREFIX):
        return _SESSIONS
    if api_key:
        return f"key:{api_key}"
    client = request.client
    if client is None:
        return _ANONYMOUS
    return f"ip:{client.host}"


async def enforce_rate_limit(
    request: Request,
    limiter: LimiterDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Reject the request when the caller has exceeded its allowance."""
    key: str = _client_key(request, x_api_key)
    retry_after: int = await limiter.admit(key)
    if retry_after == 0:
        return
    logger.warning("Rate limit exceeded for %s", key)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )
