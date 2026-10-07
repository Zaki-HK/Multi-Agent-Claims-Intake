from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    """Return UTC without tzinfo for the existing timestamp-without-time-zone columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass
