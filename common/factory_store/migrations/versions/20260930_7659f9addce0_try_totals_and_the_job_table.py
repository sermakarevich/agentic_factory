"""try totals and the job table: the attempt row keeps what the try added up to
(tokens, cost, time, counts) and its result; the job table is one row per
workflow run summed over its tries. Existing tries get zero totals.

Revision ID: 7659f9addce0
Revises: 24f8f08df70a
Create Date: 2026-09-30 11:46:25.734161
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7659f9addce0"
down_revision: str | None = "24f8f08df70a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tries", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("failure", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("turns", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("tool_failures", sa.Integer(), nullable=False),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.add_column(
        "attempt", sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "attempt", sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "attempt",
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "attempt",
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column("attempt", sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"))
    op.add_column(
        "attempt", sa.Column("duration_sec", sa.Float(), nullable=False, server_default="0")
    )
    op.add_column("attempt", sa.Column("turns", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "attempt", sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "attempt", sa.Column("tool_failures", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "attempt",
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("attempt", "result")
    op.drop_column("attempt", "tool_failures")
    op.drop_column("attempt", "tool_calls")
    op.drop_column("attempt", "turns")
    op.drop_column("attempt", "duration_sec")
    op.drop_column("attempt", "cost_usd")
    op.drop_column("attempt", "cache_write_tokens")
    op.drop_column("attempt", "cache_read_tokens")
    op.drop_column("attempt", "output_tokens")
    op.drop_column("attempt", "input_tokens")
    op.drop_table("job")
