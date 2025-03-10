"""Add quote and policy tracking fields

Revision ID: cfe3a222f6bb
Revises: 330024be7bef
Create Date: 2025-03-10 15:17:20.875852

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'cfe3a222f6bb'
down_revision = '330024be7bef'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()[f"upgrade_{engine_name}"]()


def downgrade(engine_name):
    globals()[f"downgrade_{engine_name}"]()


def upgrade_registrar():
    pass

def downgrade_registrar():
    pass


def upgrade_cloud_verifier():
    """Apply the migration: Add quote and policy tracking fields"""
    # Add nonce, last_attestation_attempt and current_backoff
    op.add_column('verifiermain', sa.Column('nonce', sa.String(length=80)))
    op.add_column('verifiermain', sa.Column('last_attestation_attempt', sa.Integer))
    op.add_column('verifiermain', sa.Column('current_backoff', sa.Integer))

    # Add the last_updated column as nullable first
    op.add_column('allowlists', sa.Column('last_updated', sa.DateTime(), nullable=True))
    op.add_column('mbpolicies', sa.Column('last_updated', sa.DateTime(), nullable=True))

    # Manually update existing rows to avoid NULL values
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE allowlists SET last_updated = NOW()"))
    conn.execute(sa.text("UPDATE mbpolicies SET last_updated = NOW()"))

    # Alter the column to make it NOT NULL after updating values
    op.alter_column('allowlists', 'last_updated', nullable=False)
    op.alter_column('mbpolicies', 'last_updated', nullable=False)


def downgrade_cloud_verifier():
    op.drop_column('allowlists', 'last_updated')
    op.drop_column('mbpolicies', 'last_updated')
    op.drop_column('verifiermain', 'nonce')
    op.drop_column('verifiermain', 'last_attestation_attempt')
    op.drop_column('verifiermain', 'current_backoff')
