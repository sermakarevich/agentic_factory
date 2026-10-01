"""the report table holds the report the coder submits: `summary` becomes
`report`, the same shape as the model-written report it held, and `result`
goes, as the job row has it already. The conversation table goes: it held
the text the report model read, rebuilt from the events.

Revision ID: 5d1e7a3b9c42
Revises: cc6c4eebce08
Create Date: 2026-10-01 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5d1e7a3b9c42"
down_revision: str | None = "cc6c4eebce08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("report") as batch:
        batch.alter_column("summary", new_column_name="report", existing_type=PAYLOAD)
        batch.drop_column("result")
    op.drop_table("conversation")


def downgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("session_id", sa.String(), sa.ForeignKey("session.id"), primary_key=True),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("events_count", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    with op.batch_alter_table("report") as batch:
        batch.alter_column("report", new_column_name="summary", existing_type=PAYLOAD)
        batch.add_column(sa.Column("result", PAYLOAD, nullable=False, server_default="{}"))
