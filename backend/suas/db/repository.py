"""Data access functions.

Repository functions return frozen domain models (``Aircraft`` / ``Payload``)
rather than leaking ORM rows into the rest of the application (Principle 2/8).
"""

from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from suas.db.models import AircraftRow, Base, PayloadRow
from suas.schemas.domain import Aircraft, Payload

_Row = TypeVar("_Row", bound=Base)
_Model = TypeVar("_Model", bound=BaseModel)


async def _get(
    session: AsyncSession, row_type: type[_Row], model: type[_Model], key: str
) -> _Model | None:
    """Fetch one row by primary key and return it as its domain model."""
    row: _Row | None = await session.get(row_type, key)
    if row is None:
        return None
    return model.model_validate(row, from_attributes=True)


async def _list(
    session: AsyncSession,
    row_type: type[_Row],
    model: type[_Model],
    order_by: InstrumentedAttribute[Any],
) -> list[_Model]:
    """Return every row of one table, in the given order, as domain models."""
    result = await session.execute(select(row_type).order_by(order_by))
    return [model.model_validate(row, from_attributes=True) for row in result.scalars().all()]


async def get_aircraft(session: AsyncSession, aircraft_id: str) -> Aircraft | None:
    """Return the aircraft with the given id, or None if absent."""
    return await _get(session, AircraftRow, Aircraft, aircraft_id)


async def get_payload(session: AsyncSession, payload_id: str) -> Payload | None:
    """Return the payload with the given id, or None if absent."""
    return await _get(session, PayloadRow, Payload, payload_id)


async def count_aircraft(session: AsyncSession) -> int:
    """Return the number of aircraft rows currently stored."""
    result = await session.execute(select(AircraftRow.id))
    return len(result.scalars().all())


async def list_aircraft(session: AsyncSession) -> list[Aircraft]:
    """Return every aircraft in the catalog, ordered by name."""
    return await _list(session, AircraftRow, Aircraft, AircraftRow.name)


async def list_payloads(session: AsyncSession) -> list[Payload]:
    """Return every payload in the catalog, ordered by weight ascending."""
    return await _list(session, PayloadRow, Payload, PayloadRow.weight_kg)
