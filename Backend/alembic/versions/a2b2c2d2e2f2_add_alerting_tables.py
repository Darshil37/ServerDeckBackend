"""Add alerting tables

Revision ID: a2b2c2d2e2f2
Revises: 0801f9906959
Create Date: 2026-06-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a2b2c2d2e2f2'
down_revision: Union[str, None] = '0801f9906959'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We must use execute because these are tenant tables and Alembic's built-in 
    # operations don't always pick up the search_path correctly if not written dynamically, 
    # but ServerDeck seems to run migrations under the standard public schema or uses a tenant schema pattern.
    # Actually, the base models use standard op.create_table. Let's use op.create_table.

    # AlertMetric Enum
    op.execute("CREATE TYPE alertmetric AS ENUM ('cpu', 'ram', 'disk', 'server_offline', 'service_down', 'ssl_expiry')")
    
    # AlertStatus Enum
    op.execute("CREATE TYPE alertstatus AS ENUM ('active', 'acknowledged', 'resolved')")
    
    # AlertUrgency Enum
    op.execute("CREATE TYPE alerturgency AS ENUM ('low', 'medium', 'high', 'critical')")

    op.create_table('alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('metric', postgresql.ENUM('cpu', 'ram', 'disk', 'server_offline', 'service_down', 'ssl_expiry', name='alertmetric', create_type=False), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('service_name', sa.String(length=255), nullable=True),
        sa.Column('ssl_domain', sa.String(length=255), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('alert_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metric_value', sa.Float(), nullable=True),
        sa.Column('status', postgresql.ENUM('active', 'acknowledged', 'resolved', name='alertstatus', create_type=False), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('alert_diagnoses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('suggested_fix', sa.Text(), nullable=True),
        sa.Column('suggested_command', sa.Text(), nullable=True),
        sa.Column('urgency', postgresql.ENUM('low', 'medium', 'high', 'critical', name='alerturgency', create_type=False), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed', sa.Boolean(), nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['alert_record_id'], ['alert_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alert_record_id')
    )


def downgrade() -> None:
    op.drop_table('alert_diagnoses')
    op.drop_table('alert_records')
    op.drop_table('alert_rules')
    
    op.execute("DROP TYPE alerturgency")
    op.execute("DROP TYPE alertstatus")
    op.execute("DROP TYPE alertmetric")
