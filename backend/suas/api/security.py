"""API-key authentication.

When any key is configured, requests must present a matching ``X-API-Key``
header, and the match names the operator making the request (#81). When no key
is configured (local development), authentication is a no-op, there is no
operator, and a warning is logged at startup.
"""

import hashlib
import hmac
import logging
import re
from typing import Annotated, Final

from fastapi import Depends, Header, HTTPException, status

from suas.config import Settings, get_settings

logger: Final[logging.Logger] = logging.getLogger(__name__)

# A session key is "session.<id>.<hex HMAC-SHA256(secret, id)>" (#82). The id is
# base64url, so it can hold neither "." nor ":", and the operator id it maps to
# ("session:...") can never collide with a configured one, which has no ":".
SESSION_KEY_PREFIX: Final[str] = "session."
_SESSION_ID: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]{22,128}")


def session_key(secret: str, session_id: str) -> str:
    """Return the backend key a browser session presents through the proxy."""
    mac = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return f"{SESSION_KEY_PREFIX}{session_id}.{mac}"


def _session_operator(presented: str, secret: str) -> str | None:
    """Return the operator a validly signed session key names, else None.

    The operator id is a digest of the session id, so the mission table never
    holds a value that could be replayed as a browser's cookie.
    """
    if not (secret and presented.startswith(SESSION_KEY_PREFIX)):
        return None
    session_id = presented[len(SESSION_KEY_PREFIX) :].rpartition(".")[0]
    if not _SESSION_ID.fullmatch(session_id):
        return None
    if not hmac.compare_digest(presented.encode(), session_key(secret, session_id).encode()):
        return None
    return f"session:{hashlib.sha256(session_id.encode()).hexdigest()[:32]}"


def _operator_for(presented: str, operator_keys: dict[str, str]) -> str | None:
    """Return the id whose key matches, comparing against every key.

    Every key is compared, match or not, so the time taken does not say how far
    down the list the presented key sits.
    """
    matched: str | None = None
    for operator_id, key in operator_keys.items():
        if hmac.compare_digest(presented.encode(), key.encode()):
            matched = operator_id
    return matched


async def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str | None:
    """Return the calling operator's id, or None when auth is off.

    Rejects a request that lacks a valid key when auth is enabled.
    """
    if not settings.auth_enabled:
        return None
    presented = x_api_key or ""
    operator_id = _session_operator(presented, settings.session_key_secret) or _operator_for(
        presented, settings.operator_keys
    )
    if x_api_key is None or operator_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return operator_id


OperatorDep = Annotated[str | None, Depends(require_api_key)]
