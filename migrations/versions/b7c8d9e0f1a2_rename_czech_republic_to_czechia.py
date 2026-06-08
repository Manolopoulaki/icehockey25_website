"""rename Czech Republic to Czechia

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-08 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE team SET name = 'Czechia' WHERE code = 'CZE' AND name = 'Czech Republic'"
    )


def downgrade():
    op.execute(
        "UPDATE team SET name = 'Czech Republic' WHERE code = 'CZE' AND name = 'Czechia'"
    )
