"""Corpus documents, screened chunks, and the quarantine they can land in.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the corpus tables."""
    op.create_table(
        "corpus_documents",
        sa.Column("document_id", sa.String(), primary_key=True),
        sa.Column("path", sa.String(), nullable=False, unique=True),
        sa.Column("sha256", sa.String(), nullable=False, unique=True),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("airframe_config_id", sa.String(), nullable=True, index=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "corpus_chunks",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("corpus_documents.document_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("airframe_config_id", sa.String(), nullable=True, index=True),
        sa.Column("field_path", sa.String(), nullable=True, index=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_table(
        "corpus_quarantine",
        sa.Column("quarantine_id", sa.String(), primary_key=True),
        sa.Column("document_path", sa.String(), nullable=False, index=True),
        sa.Column("airframe_config_id", sa.String(), nullable=True, index=True),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_by", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Drop the corpus tables."""
    op.drop_table("corpus_quarantine")
    op.drop_table("corpus_chunks")
    op.drop_table("corpus_documents")
