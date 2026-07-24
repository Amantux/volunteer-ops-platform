"""add event.is_public (opt-in public publishing)

Revision ID: c1a2b3d4e5f6
Revises: b839bf8c2bfb
Create Date: 2026-07-24 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c1a2b3d4e5f6'
down_revision: str | None = 'b839bf8c2bfb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default so the NOT NULL column backfills existing rows to "private" (opt-in
    # publishing). Then drop the server default — the ORM supplies the value on insert.
    op.add_column(
        'event',
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('event', 'is_public', server_default=None)


def downgrade() -> None:
    op.drop_column('event', 'is_public')
