"""API-key authentication.

When an API key is configured, requests must present a matching ``X-API-Key``
header. When no key is configured (local development), authentication is a
no-op and a warning is logged at startup.
"""

import hmac
import logging
from typing import Annotated, Final

from fastapi import Depends, Header, HTTPException, status

from suas.config import Settings, get_settings

logger: Final[logging.Logger] = logging.getLogger(__name__)


async def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Reject requests that lack a valid API key when auth is enabled."""
    if not settings.auth_enabled:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
