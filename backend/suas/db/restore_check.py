"""Check that every stored acknowledgement still matches what it signed (#113).

``mission_threads`` keeps the ``inputs_hash`` an operator signed; the
checkpoint keeps the sealed assessment it was signed against. A backup or
restore that separates the two keeps the signature in appearance only, so
after a restore each signed hash is compared with its checkpoint's.
"""

from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.db.models import MissionThreadRow


@dataclass(frozen=True)
class AckCheck:
    """How many stored acknowledgements were checked, and which failed."""

    checked: int
    broken: list[str] = field(default_factory=list)


async def _sealed_hash(checkpointer: BaseCheckpointSaver[Any], thread_id: str) -> str:
    """Return the checkpointed assessment's ``inputs_hash``, or ``""`` if none."""
    saved = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if saved is None:
        return ""
    assessment = dict(saved.checkpoint["channel_values"].get("assessment") or {})
    return str(assessment.get("inputs_hash", ""))


async def verify_acknowledgements(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
) -> AckCheck:
    """Compare every stored acknowledgement with its thread's checkpoint."""
    async with session_factory() as session:
        signed = (
            await session.execute(
                select(MissionThreadRow.thread_id, MissionThreadRow.ack_inputs_hash)
                .where(MissionThreadRow.ack_inputs_hash.is_not(None))
                .order_by(MissionThreadRow.thread_id)
            )
        ).all()
    broken: list[str] = []
    for thread_id, signed_hash in signed:
        sealed = await _sealed_hash(checkpointer, thread_id)
        if sealed != signed_hash:
            broken.append(
                f"{thread_id}: signed {signed_hash}, checkpoint has {sealed or 'nothing'}"
            )
    return AckCheck(checked=len(signed), broken=broken)
