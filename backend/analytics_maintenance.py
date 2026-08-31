from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from analytics import RAW_EVENT_RETENTION_DAYS
from database import SessionLocal
from models import AnalyticsDailyAggregate, AnalyticsEvent

LOCK_ID = 847_224_019


def run_retention(database: Session) -> int:
    """Aggregate and remove expired raw analytics events under a database lock."""
    dialect = database.bind.dialect.name if database.bind is not None else ""
    if dialect == "postgresql":
        acquired = database.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": LOCK_ID}
        )
        if not acquired:
            return 0

    cutoff = datetime.now(UTC) - timedelta(days=RAW_EVENT_RETENTION_DAYS)
    expired = list(
        database.scalars(
            select(AnalyticsEvent).where(AnalyticsEvent.occurred_at < cutoff)
        )
    )
    by_day: dict[object, Counter[str]] = {}
    for event in expired:
        day = event.occurred_at.date()
        by_day.setdefault(day, Counter())[event.event_type] += 1

    for day, counts in by_day.items():
        current = database.get(AnalyticsDailyAggregate, day)
        merged = Counter(current.metrics if current else {})
        merged.update(counts)
        if current:
            current.metrics = dict(merged)
            current.updated_at = datetime.now(UTC)
        else:
            database.add(AnalyticsDailyAggregate(day=day, metrics=dict(merged)))

    database.execute(delete(AnalyticsEvent).where(AnalyticsEvent.occurred_at < cutoff))
    database.commit()
    return len(expired)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run analytics retention maintenance")
    parser.parse_args()
    with SessionLocal() as database:
        removed = run_retention(database)
    print(f"Removed {removed} expired analytics events")


if __name__ == "__main__":
    main()
