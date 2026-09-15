"""Store a vector and its model identity alongside each corpus chunk.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the embedding columns.

    JSON text rather than a native vector type, so the same schema applies on
    stock Postgres, on a pgvector image, and on SQLite. See docs/retrieval.md for
    why, and for the corpus size at which that stops being the right trade.
    """
    op.add_column("corpus_chunks", sa.Column("embedding_json", sa.Text(), nullable=True))
    op.add_column("corpus_chunks", sa.Column("embedding_model", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the embedding columns."""
    op.drop_column("corpus_chunks", "embedding_model")
    op.drop_column("corpus_chunks", "embedding_json")
