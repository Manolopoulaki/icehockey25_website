"""add team table

Revision ID: a1b2c3d4e5f6
Revises: 6d0f5ed3f1a9
Create Date: 2026-06-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.team_data import iter_team_rows


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '6d0f5ed3f1a9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team',
        sa.Column('sport', sa.String(length=16), nullable=False),
        sa.Column('code', sa.String(length=3), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('name_lv', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('sport', 'code'),
    )

    team_table = sa.table(
        'team',
        sa.column('sport', sa.String),
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('name_lv', sa.String),
    )
    op.bulk_insert(
        team_table,
        [
            {'sport': sport, 'code': code, 'name': name, 'name_lv': None}
            for sport, code, name in iter_team_rows()
        ],
    )


def downgrade():
    op.drop_table('team')
