"""fix donation_campaign.status enum collision with email campaignstatus

The donations `CampaignStatus` auto-derived the Postgres type name `campaignstatus`, which already
existed for the email `CampaignStatus` (labels draft/pending_approval/...). `donation_campaign.status`
was therefore bound to the wrong enum and rejected valid values like "active". Rebind it to a
dedicated `donation_campaign_status` type. The donations tables are new, so any existing rows only
hold "draft", which casts cleanly.

Revision ID: f0e1d2c3b4a5
Revises: 03d18ac14836
Create Date: 2026-07-28 01:32:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'f0e1d2c3b4a5'
down_revision: str | None = '03d18ac14836'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW = postgresql.ENUM('draft', 'active', 'paused', 'closed', 'archived',
                       name='donation_campaign_status')
_OLD = postgresql.ENUM(name='campaignstatus', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return  # native-enum-only fix; SQLite stores enums as strings
    _NEW.create(bind, checkfirst=True)
    op.alter_column('donation_campaign', 'status', type_=_NEW,
                    existing_type=_OLD,
                    postgresql_using='status::text::donation_campaign_status')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.alter_column('donation_campaign', 'status', type_=_OLD,
                    existing_type=_NEW,
                    postgresql_using='status::text::campaignstatus')
    _NEW.drop(bind, checkfirst=True)
