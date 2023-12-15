import sqlalchemy as sa

from .. import db

games_table = db.Table(
    "games",
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("pgn", sa.Text, nullable=False),
    sa.Column("metadata", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
)
