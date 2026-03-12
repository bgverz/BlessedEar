"""initial_schema

Revision ID: d6a864810ca5
Revises:
Create Date: 2026-03-12

Captures the initial database schema for BlessedEar (users + playlists tables).
Autogenerate saw no diff because the dev SQLite file already had the tables;
this migration was written manually from the SQLAlchemy model definitions so
that a fresh PostgreSQL database can be bootstrapped cleanly via
``alembic upgrade head``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd6a864810ca5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('spotify_id', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('email', sa.String(), nullable=True, unique=True, index=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('spotify_tokens', sa.JSON(), nullable=True),
        sa.Column('preferences', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'playlists',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('spotify_playlist_id', sa.String(255), nullable=True),
        sa.Column('track_data', sa.Text(), nullable=False),
        sa.Column('mood', sa.String(50), nullable=True),
        sa.Column('generation_type', sa.String(50), nullable=True),
        sa.Column('is_exported', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('playlists')
    op.drop_table('users')
