"""Where a request comes from, and the overlap window for a rotated key.

A retired key (``SUAS_RETIRED_API_KEYS``) is accepted only until its expiry and
only from the client IP that last used it successfully, which is recorded by
key hash on every direct-key authentication. The client IP is the peer
address; ``X-Forwarded-For`` is read only when the peer is a trusted proxy.
"""

import hashlib
import hmac
import ipaddress
from datetime import datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import RetiredKey
from suas.db.dialect import upsert_insert
from suas.db.models import ApiKeyLastSeenRow


def _ip(value: str) -> str | None:
    """Return ``value`` as a canonical IP address, or None if it is not one."""
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request, trusted_proxies: frozenset[str]) -> str | None:
    """Return the caller's IP: the peer, or what a trusted peer says it forwarded.

    Hops are read right to left, skipping trusted proxies; the first other
    address is the one the nearest trusted proxy saw. Anything left of it was
    written by the client and proves nothing.
    """
    peer = _ip(request.client.host) if request.client else None
    if peer not in trusted_proxies:
        return peer
    hops = ",".join(request.headers.getlist("x-forwarded-for")).split(",")
    for hop in reversed(hops):
        address = _ip(hop)
        if address not in trusted_proxies:
            return address
    return peer


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def record_key_use(
    session_factory: async_sessionmaker[AsyncSession], key: str, ip: str | None
) -> None:
    """Remember ``ip`` as the last address ``key`` authenticated from."""
    if ip is None:
        return
    async with session_factory() as session, session.begin():
        insert = upsert_insert(session, ApiKeyLastSeenRow).values(
            key_hash=_key_hash(key), client_ip=ip
        )
        await session.execute(
            insert.on_conflict_do_update(
                index_elements=["key_hash"],
                set_={"client_ip": ip},
                where=ApiKeyLastSeenRow.client_ip != ip,
            )
        )


async def last_ip(session_factory: async_sessionmaker[AsyncSession], key: str) -> str | None:
    """Return the address ``key`` last authenticated from, if it ever did."""
    query = select(ApiKeyLastSeenRow.client_ip).where(ApiKeyLastSeenRow.key_hash == _key_hash(key))
    async with session_factory() as session:
        ip: str | None = await session.scalar(query)
    return ip


def unexpired_retired_key(
    presented: str, retired: list[RetiredKey], now: datetime
) -> RetiredKey | None:
    """Return the retired entry ``presented`` matches, if its window is open.

    Every entry is compared, as with current keys, so timing says nothing.
    """
    matched: RetiredKey | None = None
    for entry in retired:
        if hmac.compare_digest(presented.encode(), entry.key.encode()) and now < entry.expires_at:
            matched = entry
    return matched
