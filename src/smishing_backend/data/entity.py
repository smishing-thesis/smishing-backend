"""Reusable physical fields, without a new table or invented event times."""

import sqlalchemy as sa


class EntityBase:
    @staticmethod
    def primary_key():
        return sa.Column("id", sa.Uuid(), primary_key=True)

    @staticmethod
    def timestamp(name, *, key=None, server_time=False, nullable=False):
        return sa.Column(
            name,
            sa.DateTime(timezone=True),
            key=key,
            nullable=nullable,
            server_default=sa.func.now() if server_time else None,
        )
