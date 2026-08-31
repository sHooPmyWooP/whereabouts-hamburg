from uuid import uuid4

from conftest import TestSession
from fastapi.testclient import TestClient
from sqlalchemy import select

from models import Account, AnalyticsEvent, VisitorAccountLink


def register(client: TestClient, username: str = "AnalyticsAdmin") -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "valid-password"},
    )
    assert response.status_code == 201


def promote(username: str = "AnalyticsAdmin") -> None:
    with TestSession.begin() as database:
        account = database.scalar(select(Account).where(Account.username == username))
        assert account is not None
        account.is_admin = True


def event_payload(visitor_id: str, event_type: str = "mode_opened") -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "visitor_id": visitor_id,
        "event_type": event_type,
        "properties": {"mode": "daily"},
    }


def test_consented_event_is_stored_and_linked_after_login(client: TestClient) -> None:
    visitor_id = str(uuid4())
    anonymous = client.post("/api/analytics/events", json=event_payload(visitor_id))
    register(client)
    linked = client.post("/api/analytics/events", json=event_payload(visitor_id))

    assert anonymous.status_code == 202
    assert linked.status_code == 202
    with TestSession() as database:
        events = list(database.scalars(select(AnalyticsEvent)))
        link = database.get(VisitorAccountLink, visitor_id)
        assert len(events) == 2
        assert events[0].account_id is None
        assert events[1].account_id == 1
        assert link is not None and link.account_id == 1


def test_event_id_is_idempotent_and_seed_is_hmaced(client: TestClient) -> None:
    payload = event_payload(str(uuid4()), "seeded_started")
    payload["properties"] = {"seed": "My Secret Phrase"}

    first = client.post("/api/analytics/events", json=payload)
    duplicate = client.post("/api/analytics/events", json=payload)

    assert first.status_code == 202
    assert duplicate.json() == {"status": "duplicate"}
    with TestSession() as database:
        event = database.scalar(select(AnalyticsEvent))
        assert event is not None
        assert "seed" not in event.properties
        assert len(str(event.properties["seed_fingerprint"])) == 24


def test_forget_removes_raw_events_and_identity_link(client: TestClient) -> None:
    visitor_id = str(uuid4())
    register(client)
    client.post("/api/analytics/events", json=event_payload(visitor_id))

    response = client.post("/api/analytics/forget", json={"visitor_id": visitor_id})

    assert response.status_code == 204
    with TestSession() as database:
        assert database.scalar(select(AnalyticsEvent)) is None
        assert database.get(VisitorAccountLink, visitor_id) is None


def test_admin_routes_are_server_protected(client: TestClient) -> None:
    register(client)
    forbidden = client.get("/api/admin/dashboard")
    promote()
    allowed = client.get("/api/admin/dashboard?days=30")

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert "overview" in allowed.json()
    assert allowed.headers["cache-control"] == "no-store"


def test_admin_account_search_returns_limited_summary(client: TestClient) -> None:
    register(client)
    promote()

    response = client.get("/api/admin/accounts?search=analytics&sort=registered")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["username"] == "AnalyticsAdmin"
    assert "password_hash" not in body["items"][0]
