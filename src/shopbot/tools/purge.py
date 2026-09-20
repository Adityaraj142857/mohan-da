"""Purge stored screenshot files older than MEDIA_RETENTION_DAYS (SPEC 14).
Keeps hashes in the DB for duplicate detection; only deletes the files."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from shopbot.config import load_settings
from shopbot.db import Database
from shopbot.models import Screenshot


def purge(db: Database, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed = 0
    with db.session() as session:
        old_shots = session.scalars(select(Screenshot).where(Screenshot.created_at < cutoff)).all()
        for shot in old_shots:
            path = Path(shot.file_path)
            if path.exists():
                path.unlink()
                removed += 1
    return removed


def main() -> None:
    settings = load_settings()
    db = Database(settings)
    removed = purge(db, settings.media_retention_days)
    print(f"Purged {removed} screenshot file(s) older than {settings.media_retention_days} days.")


if __name__ == "__main__":
    main()
