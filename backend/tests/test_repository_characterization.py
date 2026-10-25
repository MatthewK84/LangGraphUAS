"""Characterization tests for the repository read functions.

They pin what get_aircraft, get_payload, list_aircraft and list_payloads return
before the four are folded onto shared helpers: frozen domain models, never ORM
rows, None for an unknown id, and each list's ordering.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.db.repository import get_aircraft, get_payload, list_aircraft, list_payloads
from suas.reference_data import load_rows
from suas.schemas.domain import Aircraft, Payload


def _seed(filename: str) -> list[dict[str, Any]]:
    """The rows conftest seeds, from the loader production uses."""
    return load_rows(filename)


async def test_get_aircraft_returns_the_domain_model_or_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        found = await get_aircraft(session, "Skydio_X10D")
        missing = await get_aircraft(session, "nope")

    assert type(found) is Aircraft
    assert found.id == "Skydio_X10D"
    assert missing is None


async def test_get_payload_returns_the_domain_model_or_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    expected = next(record for record in _seed("payloads.json") if record["id"] == "None")
    async with session_factory() as session:
        found = await get_payload(session, "None")
        missing = await get_payload(session, "nope")

    assert type(found) is Payload
    assert found.model_dump() == Payload.model_validate(expected).model_dump()
    assert missing is None


async def test_list_aircraft_returns_every_airframe_ordered_by_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        catalog = await list_aircraft(session)

    assert all(type(item) is Aircraft for item in catalog)
    assert [item.name for item in catalog] == sorted(
        str(record["name"]) for record in _seed("aircraft.json")
    )


async def test_list_payloads_returns_every_payload_lightest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        catalog = await list_payloads(session)

    assert all(type(item) is Payload for item in catalog)
    assert sorted(item.id for item in catalog) == sorted(
        str(record["id"]) for record in _seed("payloads.json")
    )
    weights = [item.weight_kg for item in catalog]
    assert weights == sorted(weights)
    assert len(set(weights)) > 1
