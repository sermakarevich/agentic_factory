"""the structured_output table: for a job a workflow asked for structured output,
the JSON schema it asked for, the output the extraction step found and where
it found it (last_message | conversation). One row per session.

Revision ID: 9410ff787989
Revises: 7659f9addce0
Create Date: 2026-09-30 20:41:28.412434
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9410ff787989"
down_revision: str | None = "7659f9addce0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "structured_output",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "schema",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "structured_output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )


def downgrade() -> None:
    op.drop_table("structured_output")
