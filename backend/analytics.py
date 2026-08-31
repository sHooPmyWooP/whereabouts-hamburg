from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from collections import defaultdict, deque
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from auth_routes import get_optional_account
from database import get_db
from models import (
    Account,
    AnalyticsEvent,
    GameDailyDistricts,
    TrainingAttempt,
    TrainingSession,
    VisitorAccountLink,
)

NO_STORE_HEADERS = {"Cache-Control": "no-store"}
HAMBURG = ZoneInfo("Europe/Berlin")
RAW_EVENT_RETENTION_DAYS = 397
ALLOWED_EVENTS = {
    "app_opened",
    "mode_opened",
    "daily_started",
    "daily_completed",
    "seeded_started",
    "seeded_completed",
    "daily_result_shared",
    "seeded_result_shared",
    "account_authenticated",
}
ALLOWED_PROPERTIES = {
    "mode",
    "reason",
    "pins_solved",
    "guesses_spent",
    "seed",
    "device_class",
    "browser_language",
    "referrer_domain",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "method",
}
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_EVENTS = 120
_event_requests: dict[str, deque[datetime]] = defaultdict(deque)

ADMIN_SORTS = {
    "last_active": "last_active",
    "registered": "registered",
    "active_days": "active_days",
    "daily_completions": "daily_completions",
    "training_attempts": "training_attempts",
}

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


class EventRequest(BaseModel):
    event_id: uuid.UUID
    visitor_id: uuid.UUID
    event_type: str = Field(max_length=40)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if value not in ALLOWED_EVENTS:
            raise ValueError("Unsupported analytics event")
        return value

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not set(value).issubset(ALLOWED_PROPERTIES):
            raise ValueError("Unsupported analytics property")
        if len(value) > 10:
            raise ValueError("Too many analytics properties")
        for item in value.values():
            if not isinstance(item, (str, int, float, bool)) or isinstance(item, str) and len(item) > 160:
                raise ValueError("Invalid analytics property value")
        return value


class DeleteVisitorRequest(BaseModel):
    visitor_id: uuid.UUID


def _excluded_account_ids() -> set[int]:
    raw = os.getenv("ANALYTICS_EXCLUDED_ACCOUNT_IDS", "")
    return {int(value.strip()) for value in raw.split(",") if value.strip().isdigit()}


def _seed_fingerprint(seed: str) -> str:
    secret = os.environ["SESSION_SECRET"].encode()
    normalized = seed.strip().lower().encode()
    return hmac.new(secret, normalized, hashlib.sha256).hexdigest()[:24]


def _sanitize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(properties)
    seed = cleaned.pop("seed", None)
    if isinstance(seed, str):
        cleaned["seed_fingerprint"] = _seed_fingerprint(seed)
    referrer = cleaned.get("referrer_domain")
    if isinstance(referrer, str):
        cleaned["referrer_domain"] = urlparse(
            referrer if "://" in referrer else f"https://{referrer}"
        ).hostname or ""
    return cleaned


def require_admin(
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> Account:
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not account.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return account


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def collect_event(
    request: EventRequest,
    response: Response,
    http_request: Request,
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> dict[str, str]:
    """Store one consented, allowlisted product event idempotently."""
    response.headers.update(NO_STORE_HEADERS)
    client_key = http_request.client.host if http_request.client else "unknown"
    now = datetime.now(UTC)
    recent = _event_requests[client_key]
    cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    while recent and recent[0] < cutoff:
        recent.popleft()
    if len(recent) >= RATE_LIMIT_EVENTS:
        raise HTTPException(status_code=429, detail="Too many analytics events")
    recent.append(now)

    event_id = str(request.event_id)
    if database.scalar(select(AnalyticsEvent.id).where(AnalyticsEvent.event_id == event_id)):
        return {"status": "duplicate"}
    visitor_id = str(request.visitor_id)
    account_id = account.id if account is not None else None
    database.add(
        AnalyticsEvent(
            event_id=event_id,
            visitor_id=visitor_id,
            account_id=account_id,
            event_type=request.event_type,
            properties=_sanitize_properties(request.properties),
        )
    )
    if account_id is not None:
        link = database.get(VisitorAccountLink, visitor_id)
        if link is None:
            database.add(VisitorAccountLink(visitor_id=visitor_id, account_id=account_id))
        else:
            link.account_id = account_id
    database.commit()
    return {"status": "accepted"}


@router.post("/forget", status_code=status.HTTP_204_NO_CONTENT)
def forget_visitor(
    request: DeleteVisitorRequest,
    database: Annotated[Session, Depends(get_db)],
) -> Response:
    """Delete identifiable raw telemetry for a browser that revoked consent."""
    visitor_id = str(request.visitor_id)
    database.execute(delete(AnalyticsEvent).where(AnalyticsEvent.visitor_id == visitor_id))
    database.execute(delete(VisitorAccountLink).where(VisitorAccountLink.visitor_id == visitor_id))
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=NO_STORE_HEADERS)


@router.get("/config")
def analytics_config(response: Response) -> dict[str, str]:
    response.headers.update(NO_STORE_HEADERS)
    return {"privacy_contact_email": os.getenv("PRIVACY_CONTACT_EMAIL", "")}


@admin_router.get("/access")
def admin_access(
    response: Response,
    _account: Annotated[Account, Depends(require_admin)],
) -> dict[str, bool]:
    response.headers.update(NO_STORE_HEADERS)
    return {"is_admin": True}


def _event_player_key(event: AnalyticsEvent, links: dict[str, int]) -> str:
    account_id = event.account_id or links.get(event.visitor_id)
    return f"account:{account_id}" if account_id else f"visitor:{event.visitor_id}"


def _period_start(days: int) -> datetime | None:
    if days == 0:
        return None
    today = datetime.now(HAMBURG).date()
    return datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), HAMBURG).astimezone(UTC)


@admin_router.get("/dashboard")
def admin_dashboard(
    response: Response,
    database: Annotated[Session, Depends(get_db)],
    _account: Annotated[Account, Depends(require_admin)],
    days: Annotated[int, Query(ge=0, le=90)] = 30,
) -> dict[str, Any]:
    """Return privacy-bounded usage aggregates for the selected period."""
    response.headers.update(NO_STORE_HEADERS)
    if days not in {0, 7, 30, 90}:
        raise HTTPException(status_code=422, detail="Unsupported date range")
    start = _period_start(days)
    excluded = _excluded_account_ids()

    event_query = select(AnalyticsEvent)
    if start is not None:
        event_query = event_query.where(AnalyticsEvent.occurred_at >= start)
    events = [
        event for event in database.scalars(event_query)
        if event.account_id not in excluded
    ]
    links = {
        link.visitor_id: link.account_id
        for link in database.scalars(select(VisitorAccountLink))
        if link.account_id not in excluded
    }
    players = {_event_player_key(event, links) for event in events}
    anonymous_players = {
        event.visitor_id for event in events
        if event.account_id is None and event.visitor_id not in links
    }
    consented_accounts = {
        event.account_id or links.get(event.visitor_id)
        for event in events
        if event.account_id or links.get(event.visitor_id)
    }

    account_query = select(Account)
    if start is not None:
        account_query = account_query.where(Account.created_at >= start)
    new_accounts = [account for account in database.scalars(account_query) if account.id not in excluded]

    game_query = select(GameDailyDistricts)
    attempt_query = select(TrainingAttempt)
    session_query = select(TrainingSession)
    if start is not None:
        game_query = game_query.where(GameDailyDistricts.created_at >= start)
        attempt_query = attempt_query.where(TrainingAttempt.created_at >= start)
        session_query = session_query.where(TrainingSession.created_at >= start)
    games = [game for game in database.scalars(game_query) if game.account_id not in excluded]
    attempts = [attempt for attempt in database.scalars(attempt_query) if attempt.account_id not in excluded]
    sessions = [session for session in database.scalars(session_query) if session.account_id not in excluded]

    event_counts: dict[str, int] = defaultdict(int)
    daily_players: dict[date, set[str]] = defaultdict(set)
    player_days: dict[str, set[date]] = defaultdict(set)
    modes: dict[str, set[str]] = defaultdict(set)
    seeded: dict[str, dict[str, Any]] = {}
    for event in events:
        event_counts[event.event_type] += 1
        key = _event_player_key(event, links)
        local_day = event.occurred_at.astimezone(HAMBURG).date()
        daily_players[local_day].add(key)
        player_days[key].add(local_day)
        mode = event.properties.get("mode")
        if event.event_type == "mode_opened" and isinstance(mode, str):
            modes[mode].add(key)
        fingerprint = event.properties.get("seed_fingerprint")
        if isinstance(fingerprint, str):
            bucket = seeded.setdefault(fingerprint, {"players": set(), "opens": 0, "starts": 0, "completions": 0})
            bucket["players"].add(key)
            if event.event_type == "mode_opened":
                bucket["opens"] += 1
            elif event.event_type == "seeded_started":
                bucket["starts"] += 1
            elif event.event_type == "seeded_completed":
                bucket["completions"] += 1

    completed_games = [game for game in games if game.status == "finished"]
    abandoned_games = [
        game
        for game in games
        if game.status == "in_progress"
        and game.created_at < datetime.now(UTC) - timedelta(hours=24)
    ]
    solved_total = sum(len(game.solved_pin_indices) for game in games)
    guesses_spent = sum(10 - game.budget_remaining for game in games)
    daily_rows = [
        {"date": day.isoformat(), "players": len(day_players)}
        for day, day_players in sorted(daily_players.items())
    ]
    returning = sum(len(active_days) >= 2 for active_days in player_days.values())
    correct_attempts = sum(attempt.outcome == "correct" for attempt in attempts)
    returning_learners = len({
        account_id for account_id in {attempt.account_id for attempt in attempts}
        if len({attempt.created_at.astimezone(HAMBURG).date() for attempt in attempts if attempt.account_id == account_id}) >= 2
    })

    return {
        "range_days": days,
        "overview": {
            "consented_players": len(players),
            "consented_anonymous_players": len(anonymous_players),
            "consented_accounts": len(consented_accounts),
            "new_accounts": len(new_accounts),
            "returning_player_rate": round(returning / len(players) * 100, 1) if players else 0,
        },
        "daily_players": daily_rows,
        "modes": {mode: len(mode_players) for mode, mode_players in modes.items()},
        "daily": {
            "account_starts": len(games),
            "account_completions": len(completed_games),
            "account_abandoned": len(abandoned_games),
            "completion_rate": round(len(completed_games) / len(games) * 100, 1) if games else 0,
            "give_up_rate": round(sum(game.finish_reason == "gave_up" for game in games) / len(games) * 100, 1) if games else 0,
            "average_pins_solved": round(solved_total / len(games), 1) if games else 0,
            "average_guesses_spent": round(guesses_spent / len(games), 1) if games else 0,
            "consented_starts": event_counts["daily_started"],
            "consented_completions": event_counts["daily_completed"],
        },
        "training": {
            "sessions": len(sessions),
            "engaged_sessions": sum(session.attempt_count > 0 for session in sessions),
            "attempts": len(attempts),
            "accuracy": round(correct_attempts / len(attempts) * 100, 1) if attempts else 0,
            "returning_learners": returning_learners,
        },
        "seeded_challenges": [
            {
                "fingerprint": fingerprint,
                "players": len(values["players"]),
                "opens": values["opens"],
                "starts": values["starts"],
                "completions": values["completions"],
            }
            for fingerprint, values in seeded.items()
        ],
    }


@admin_router.get("/accounts")
def admin_accounts(
    response: Response,
    database: Annotated[Session, Depends(get_db)],
    _account: Annotated[Account, Depends(require_admin)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str, Query(max_length=32)] = "",
    sort: Annotated[str, Query()] = "last_active",
    direction: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> dict[str, Any]:
    """Return a read-only, paginated Account activity summary."""
    response.headers.update(NO_STORE_HEADERS)
    if sort not in ADMIN_SORTS:
        raise HTTPException(status_code=422, detail="Unsupported sort")
    excluded = _excluded_account_ids()
    query = select(Account)
    if search.strip():
        query = query.where(func.lower(Account.username).contains(search.strip().lower()))
    accounts = [account for account in database.scalars(query) if account.id not in excluded]

    rows: list[dict[str, Any]] = []
    for account in accounts:
        games = list(database.scalars(select(GameDailyDistricts).where(GameDailyDistricts.account_id == account.id)))
        attempts = list(database.scalars(select(TrainingAttempt).where(TrainingAttempt.account_id == account.id)))
        activity_times = [account.created_at]
        activity_times.extend(game.finished_at or game.created_at for game in games)
        activity_times.extend(attempt.created_at for attempt in attempts)
        if account.last_login_at:
            activity_times.append(account.last_login_at)
        active_days = {
            timestamp.astimezone(HAMBURG).date() for timestamp in activity_times
        }
        rows.append({
            "id": account.id,
            "username": account.username,
            "registered": account.created_at,
            "last_active": max(activity_times),
            "last_login": account.last_login_at,
            "active_days": len(active_days),
            "daily_completions": sum(game.status == "finished" for game in games),
            "training_attempts": len(attempts),
            "is_admin": account.is_admin,
        })
    rows.sort(key=lambda row: row[ADMIN_SORTS[sort]], reverse=direction == "desc")
    page_size = 50
    start_index = (page - 1) * page_size
    return {"items": rows[start_index:start_index + page_size], "page": page, "page_size": page_size, "total": len(rows)}
