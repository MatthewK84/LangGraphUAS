"""SQLAlchemy ORM models.

Uses the typed 2.0 ``Mapped`` style so column types are visible to mypy
(Principle 8).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class AircraftRow(Base):
    """Persistent aircraft reference record."""

    __tablename__ = "aircraft"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    max_payload_kg: Mapped[float] = mapped_column(Float, nullable=False)
    battery_wh: Mapped[float] = mapped_column(Float, nullable=False)
    max_wind_mps: Mapped[float] = mapped_column(Float, nullable=False)
    cruise_speed_mps: Mapped[float] = mapped_column(Float, nullable=False)
    hover_power_w: Mapped[float] = mapped_column(Float, nullable=False)
    cruise_power_w: Mapped[float] = mapped_column(Float, nullable=False)
    max_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    min_temp_c: Mapped[float] = mapped_column(Float, nullable=False, server_default="-20.0")
    # Nullable: most airframes have no documented pack takeoff procedure, and
    # absence of a limit is not a limit of zero.
    pack_min_takeoff_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Where each number came from, keyed by field name. Read by the operational
    # gate: a figure that is not from a datasheet or a flight log blocks
    # operational mode. JSON rather than columns because the shape is per-field
    # and belongs to the data, not the schema.
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class PayloadRow(Base):
    """Persistent payload reference record."""

    __tablename__ = "payloads"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    power_draw_w: Mapped[float] = mapped_column(Float, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class MissionThreadRow(Base):
    """Creation time of a planning thread, used to age out checkpoints.

    LangGraph's checkpoint tables carry no timestamp we can portably query, so
    the application records when each thread was first planned. Retention reads
    this table to decide what to delete via the checkpointer's own API rather
    than reaching into its internal schema.
    """

    __tablename__ = "mission_threads"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Who signed off on what. The hash and calculator version pin the
    # acknowledgement to the exact assessment it was given: if either changes,
    # the signature no longer describes the mission and must be taken again.
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ack_actor: Mapped[str | None] = mapped_column(String, nullable=True)
    ack_action: Mapped[str | None] = mapped_column(String, nullable=True)
    ack_inputs_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    ack_calculator_version: Mapped[str | None] = mapped_column(String, nullable=True)

    # How many replans this briefed thread has spawned. Each gets its own
    # child thread, so the briefed assessment stays addressable and immutable.
    replan_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class FlightLogRow(Base):
    """An uploaded flight log and the power estimates derived from it.

    The raw file is kept alongside the estimates. A measured figure that cannot
    be traced back to the recording it came from is not much better than an
    estimate, and ``sha256`` is unique so re-uploading the same file cannot
    produce a second, divergent set of numbers.
    """

    __tablename__ = "flight_logs"

    log_id: Mapped[str] = mapped_column(String, primary_key=True)
    airframe_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    raw_csv: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hover_median_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    hover_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hover_confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    cruise_median_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    cruise_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cruise_confidence: Mapped[str | None] = mapped_column(String, nullable=True)

    # Whether these estimates were written into the airframe's reference row.
    # Ingesting a log and changing the numbers a plan is built on are separate
    # acts, and this records which one happened.
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FlightLogSampleRow(Base):
    """One parsed telemetry sample, kept so an estimate can be re-derived."""

    __tablename__ = "flight_log_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(
        String, ForeignKey("flight_logs.log_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    alt_m: Mapped[float] = mapped_column(Float, nullable=False)
    power_w: Mapped[float] = mapped_column(Float, nullable=False)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    phase: Mapped[str] = mapped_column(String, nullable=False)


class CorpusDocumentRow(Base):
    """A document the manifest vouched for, and that passed verification."""

    __tablename__ = "corpus_documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    airframe_config_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CorpusChunkRow(Base):
    """One screened, normalised chunk of a document.

    No embedding column yet. Retrieval is a later change, and a nullable vector
    on every row would imply this table already supports a search it does not.
    """

    __tablename__ = "corpus_chunks"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("corpus_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    airframe_config_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    field_path: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class CorpusQuarantineRow(Base):
    """A chunk that tripped the screener, kept rather than discarded.

    Its presence blocks operational mode for the configuration it belongs to.
    A document containing something that reads as an instruction to a model is
    not paperwork anyone should fly on until a person has looked at it.
    """

    __tablename__ = "corpus_quarantine"

    quarantine_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    airframe_config_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    quarantined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_by: Mapped[str | None] = mapped_column(String, nullable=True)
