import asyncio
import contextlib
import os
from datetime import date, datetime
from pathlib import Path as FilePath
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload
from starlette.exceptions import HTTPException as StarletteHTTPException

from analytics import admin_router
from analytics import router as analytics_router
from analytics_maintenance import run_retention
from auth_routes import get_optional_account
from auth_routes import router as auth_router
from daily_challenge import (
    GENERATION_VERSION,
    INITIAL_BUDGET,
    AnonymousGameState,
    DailyChallengeError,
    DailyChallengeGames,
    DailyChallengeSnapshot,
    SubmittedGuess,
)
from database import SessionLocal, engine, get_db
from game import PIN_COUNT, ChallengeGenerator, DistrictCatalog
from models import Account, GameDailyDistricts
from training import create_training_router

load_dotenv()

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"
STATIC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)

catalog = DistrictCatalog.load()


def load_fun_facts() -> dict[str, list[str]]:
    """Load and validate the display facts bundled with the district catalog."""
    facts_path = FilePath(__file__).resolve().parent.parent / "data" / "hamburg-stadtteil-fun-facts.yaml"
    with facts_path.open(encoding="utf-8") as source:
        payload = yaml.safe_load(source)

    facts = payload.get("facts") if isinstance(payload, dict) else None
    expected_names = {district.name for district in catalog.districts}
    if not isinstance(facts, dict) or set(facts) != expected_names:
        raise ValueError("Fun facts must contain exactly one entry for every Stadtteil")
    if any(
        not isinstance(items, list)
        or not 1 <= len(items) <= 5
        or any(not isinstance(item, str) or not item.strip() for item in items)
        for items in facts.values()
    ):
        raise ValueError("Each Stadtteil needs between one and five non-empty fun facts")
    return facts


fun_facts = load_fun_facts()
challenge_generator = ChallengeGenerator(catalog)
daily_challenge_games = DailyChallengeGames(catalog, challenge_generator)

app = FastAPI(
    title="Hamburg Whereabouts API",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.include_router(auth_router)
app.include_router(analytics_router)
app.include_router(admin_router)
app.include_router(create_training_router(catalog))
maintenance_task: asyncio.Task[None] | None = None


async def analytics_maintenance_loop() -> None:
    """Run retention daily without requiring another deployment service."""
    while True:
        with SessionLocal() as database:
            run_retention(database)
        await asyncio.sleep(24 * 60 * 60)


@app.on_event("startup")
async def start_analytics_maintenance() -> None:
    global maintenance_task
    if IS_PRODUCTION:
        if not os.getenv("PRIVACY_CONTACT_EMAIL", "").strip():
            raise RuntimeError("PRIVACY_CONTACT_EMAIL is required in production")
        maintenance_task = asyncio.create_task(analytics_maintenance_loop())


@app.on_event("shutdown")
async def stop_analytics_maintenance() -> None:
    if maintenance_task is not None:
        maintenance_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance_task


@app.exception_handler(StarletteHTTPException)
def coded_http_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
    """Expose diagnostic detail alongside a stable client-facing error code."""
    return JSONResponse(
        status_code=error.status_code,
        content={
            "detail": error.detail,
            "code": getattr(error, "code", f"http.{error.status_code}"),
        },
        headers=error.headers,
    )


@app.exception_handler(RequestValidationError)
def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(error.errors()),
            "code": "request.validation",
        },
    )


@app.exception_handler(DailyChallengeError)
def daily_challenge_error(
    _request: Request, error: DailyChallengeError
) -> JSONResponse:
    """Render Daily Challenge policy failures at the HTTP seam."""
    return JSONResponse(
        status_code=error.status_code,
        content={
            "detail": error.detail,
            "code": error.code or f"http.{error.status_code}",
        },
    )


class SPAStaticFiles(StaticFiles):
    """Serve the client entry point for browser requests to SPA routes."""

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if (
                error.status_code != 404
                or path.startswith("api/")
                or os.path.splitext(path)[1]
            ):
                raise
        return await super().get_response("index.html", scope)


@app.exception_handler(OperationalError)
def database_unavailable(
    _request: Request, _error: OperationalError
) -> JSONResponse:
    """Return a sanitized, non-cacheable response when PostgreSQL is unavailable."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Account service temporarily unavailable. Please try again.",
            "code": "service.database_unavailable",
        },
        headers={"Cache-Control": "no-store", "Retry-After": "5"},
    )


if not IS_PRODUCTION:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database")
def database_health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


class DistrictSummary(BaseModel):
    id: int
    name: str
    bezirk: str


class MapDistrict(DistrictSummary):
    boundary: dict[str, Any]


class ExploreDistrict(DistrictSummary):
    fun_facts: list[str]


class PublicPin(BaseModel):
    index: int
    lat: float
    lng: float


class DailyResponse(BaseModel):
    generation_version: str
    date: date
    pins: list[PublicPin]
    initial_budget: int
    budget_remaining: int
    solved_pins: list[Any]
    missed_districts: list[dict[str, Any]]
    guess_history: list[dict[str, Any]]
    status: Literal["in_progress", "finished"]
    state_source: Literal["anonymous", "account"]
    finish_reason: Literal["solved", "budget", "gave_up"] | None


class SeededChallengeResponse(BaseModel):
    generation_version: str
    seed: str
    pins: list[PublicPin]
    initial_budget: int
    budget_remaining: int
    solved_pins: list[Any]
    status: Literal["in_progress", "finished"]


class AnonymousState(BaseModel):
    budget_remaining: int = Field(ge=1, le=INITIAL_BUDGET)
    solved_pin_indices: list[int] = Field(default_factory=list, max_length=PIN_COUNT)

    @model_validator(mode="after")
    def validate_indices(self) -> "AnonymousState":
        if len(self.solved_pin_indices) != len(set(self.solved_pin_indices)):
            raise ValueError("Solved Pin indices must be unique")
        if any(index < 0 or index >= PIN_COUNT for index in self.solved_pin_indices):
            raise ValueError("Solved Pin index is out of range")
        if len(self.solved_pin_indices) == PIN_COUNT:
            raise ValueError("The Daily Challenge is already finished")
        return self


class GuessRequest(BaseModel):
    challenge_date: date
    guessed_district_id: int
    anonymous_state: AnonymousState | None = None


class SeededGuessRequest(BaseModel):
    guessed_district_id: int
    anonymous_state: AnonymousState


class DailyGiveUpRequest(BaseModel):
    challenge_date: date
    anonymous_state: AnonymousState | None = None


class SeededGiveUpRequest(BaseModel):
    anonymous_state: AnonymousState


class GuessResponse(BaseModel):
    correct: bool
    solved_pin_index: int | None
    distance_km: float | None
    missed_district: dict[str, Any] | None
    budget_remaining: int
    status: Literal["in_progress", "finished"]
    reveals: list[dict[str, Any]]


class GiveUpResponse(BaseModel):
    budget_remaining: int
    status: Literal["finished"]
    reveals: list[dict[str, Any]]


class AdoptAnonymousGuess(BaseModel):
    district_id: int


class AdoptAnonymousDailyRequest(BaseModel):
    challenge_date: date
    budget_remaining: int = Field(ge=0, le=INITIAL_BUDGET)
    solved_pin_indices: list[int] = Field(default_factory=list, max_length=PIN_COUNT)
    guesses: list[AdoptAnonymousGuess] = Field(default_factory=list, max_length=INITIAL_BUDGET)

    @model_validator(mode="after")
    def validate_indices(self) -> "AdoptAnonymousDailyRequest":
        if len(self.solved_pin_indices) != len(set(self.solved_pin_indices)):
            raise ValueError("Solved Pin indices must be unique")
        if any(index < 0 or index >= PIN_COUNT for index in self.solved_pin_indices):
            raise ValueError("Solved Pin index is out of range")
        return self


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    pins_solved: int
    guesses_used: int
    total_missed_distance_km: float
    is_you: bool


class LeaderboardResponse(BaseModel):
    date: date
    player_count: int
    entries: list[LeaderboardEntry]
    context_entries: list[LeaderboardEntry]
    your_entry: LeaderboardEntry
    offset: int
    limit: int


def current_challenge_date() -> date:
    """Return the current Daily Challenge date in Hamburg."""
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def leaderboard_entries(database: Session, challenge_date: date, account_id: int) -> list[LeaderboardEntry]:
    """Build one deterministic, shared-rank table for a Daily Challenge."""
    games = database.scalars(
        select(GameDailyDistricts)
        .options(selectinload(GameDailyDistricts.guesses), selectinload(GameDailyDistricts.account))
        .where(
            GameDailyDistricts.challenge_date == challenge_date,
            GameDailyDistricts.status == "finished",
        )
    ).all()
    scored: list[tuple[GameDailyDistricts, int, int, float]] = []
    for game in games:
        pins_solved = len(game.solved_pin_indices)
        guesses_used = INITIAL_BUDGET - game.budget_remaining
        # Legacy rows have only a one-decimal kilometre value. New rows retain
        # the exact metric distance, while both display at one decimal km.
        total_meters = sum(
            guess.distance_meters
            if guess.distance_meters is not None
            else (guess.distance_km or 0) * 1000
            for guess in game.guesses
            if not guess.was_correct
        )
        scored.append((game, pins_solved, guesses_used, total_meters))

    scored.sort(key=lambda item: (-item[1], item[2], item[3], item[0].account.username.casefold()))
    entries: list[LeaderboardEntry] = []
    previous_score: tuple[int, int, float] | None = None
    rank = 0
    for position, (game, pins_solved, guesses_used, total_meters) in enumerate(scored, start=1):
        score = (pins_solved, guesses_used, total_meters)
        if score != previous_score:
            rank = position
            previous_score = score
        entries.append(LeaderboardEntry(
            rank=rank,
            username=game.account.username,
            pins_solved=pins_solved,
            guesses_used=guesses_used,
            total_missed_distance_km=round(total_meters / 1000, 1),
            is_you=game.account_id == account_id,
        ))
    return entries


@app.get("/api/leaderboard/dates", response_model=list[date])
def leaderboard_dates(
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account, Depends(get_optional_account)],
) -> list[date]:
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return list(database.scalars(
        select(GameDailyDistricts.challenge_date)
        .where(GameDailyDistricts.account_id == account.id, GameDailyDistricts.status == "finished")
        .order_by(GameDailyDistricts.challenge_date.desc())
    ))


@app.get("/api/leaderboard/{challenge_date}", response_model=LeaderboardResponse)
def get_leaderboard(
    challenge_date: date,
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account, Depends(get_optional_account)],
    offset: int = 0,
    limit: int = 50,
) -> LeaderboardResponse:
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    played = database.scalar(select(GameDailyDistricts.id).where(
        GameDailyDistricts.account_id == account.id,
        GameDailyDistricts.challenge_date == challenge_date,
        GameDailyDistricts.status == "finished",
    ))
    if played is None:
        raise HTTPException(status_code=403, detail="Finish this Daily Challenge to view its leaderboard")
    if offset < 0 or limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="offset and limit are out of range")
    entries = leaderboard_entries(database, challenge_date, account.id)
    your_index = next(index for index, entry in enumerate(entries) if entry.is_you)
    yours = entries[your_index]
    context = entries[:3] + entries[max(0, your_index - 2):your_index + 3]
    context_by_name = {entry.username: entry for entry in context}
    context = sorted(context_by_name.values(), key=lambda entry: (entry.rank, entry.username.casefold()))
    return LeaderboardResponse(
        date=challenge_date,
        player_count=len(entries),
        entries=entries[offset:offset + limit],
        context_entries=context,
        your_entry=yours,
        offset=offset,
        limit=limit,
    )


@app.get("/api/districts", response_model=list[DistrictSummary])
def list_districts() -> list[DistrictSummary]:
    return [
        DistrictSummary(id=district.id, name=district.name, bezirk=district.bezirk)
        for district in catalog.districts
    ]


@app.get("/api/map/districts/v1", response_model=list[MapDistrict])
def map_districts(response: Response) -> list[MapDistrict]:
    """Return versioned Stadtteil geometry shared by every map mode."""
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return [
        MapDistrict(
            id=district.id,
            name=district.name,
            bezirk=district.bezirk,
            boundary=district.boundary,
        )
        for district in catalog.districts
    ]


@app.get("/api/explore/districts", response_model=list[ExploreDistrict])
def explore_districts(response: Response) -> list[ExploreDistrict]:
    """Return the lightweight facts used only by the interactive explorer."""
    response.headers["Cache-Control"] = "public, max-age=86400"
    return [
        ExploreDistrict(
            id=district.id,
            name=district.name,
            bezirk=district.bezirk,
            fun_facts=fun_facts[district.name],
        )
        for district in catalog.districts
    ]


def _anonymous_game_state(state: AnonymousState | None) -> AnonymousGameState | None:
    if state is None:
        return None
    return AnonymousGameState(
        budget_remaining=state.budget_remaining,
        solved_pin_indices=tuple(state.solved_pin_indices),
    )


def _daily_response(snapshot: DailyChallengeSnapshot) -> DailyResponse:
    return DailyResponse(
        generation_version=GENERATION_VERSION,
        date=snapshot.challenge_date,
        pins=[
            PublicPin(index=pin.index, lat=pin.point.y, lng=pin.point.x)
            for pin in snapshot.pins
        ],
        initial_budget=INITIAL_BUDGET,
        budget_remaining=snapshot.budget_remaining,
        solved_pins=snapshot.solved_pins,
        missed_districts=snapshot.missed_districts,
        guess_history=snapshot.guess_history,
        status=snapshot.status,
        state_source=snapshot.state_source,
        finish_reason=snapshot.finish_reason,
    )


@app.get("/api/daily", response_model=DailyResponse)
def get_daily(
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> DailyResponse:
    """Return public Pins plus identity-scoped Daily Challenge progress."""
    return _daily_response(
        daily_challenge_games.daily_snapshot(
            database, account, current_challenge_date()
        )
    )


@app.get("/api/challenges/{seed}", response_model=SeededChallengeResponse)
def get_seeded_challenge(
    seed: str = Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
) -> SeededChallengeResponse:
    snapshot = daily_challenge_games.seeded_snapshot(seed)
    return SeededChallengeResponse(
        generation_version=GENERATION_VERSION,
        seed=snapshot.seed,
        pins=[
            PublicPin(index=pin.index, lat=pin.point.y, lng=pin.point.x)
            for pin in snapshot.pins
        ],
        initial_budget=INITIAL_BUDGET,
        budget_remaining=INITIAL_BUDGET,
        solved_pins=[],
        status="in_progress",
    )


@app.post("/api/daily/adopt", response_model=DailyResponse)
def adopt_anonymous_daily(
    request: AdoptAnonymousDailyRequest,
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> DailyResponse:
    """Persist a completed anonymous result after an explicit account sign-in."""
    snapshot = daily_challenge_games.adopt_anonymous(
        database=database,
        account=account,
        challenge_date=request.challenge_date,
        today=current_challenge_date(),
        budget_remaining=request.budget_remaining,
        solved_pin_indices=request.solved_pin_indices,
        guesses=[SubmittedGuess(district_id=item.district_id) for item in request.guesses],
    )
    return _daily_response(snapshot)


@app.post("/api/daily/guess", response_model=GuessResponse)
def submit_guess(
    request: GuessRequest,
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> GuessResponse:
    """Evaluate a Guess using Account state or validated anonymous state."""
    result = daily_challenge_games.guess_daily(
        database=database,
        account=account,
        challenge_date=request.challenge_date,
        today=current_challenge_date(),
        guessed_district_id=request.guessed_district_id,
        anonymous_state=_anonymous_game_state(request.anonymous_state),
    )
    return GuessResponse(**result.__dict__)


@app.post("/api/daily/give-up", response_model=GiveUpResponse)
def give_up_daily(
    request: DailyGiveUpRequest,
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> GiveUpResponse:
    """Finish today's Daily Challenge without trusting Account browser state."""
    result = daily_challenge_games.give_up_daily(
        database=database,
        account=account,
        challenge_date=request.challenge_date,
        today=current_challenge_date(),
        anonymous_state=_anonymous_game_state(request.anonymous_state),
    )
    return GiveUpResponse(
        budget_remaining=result.budget_remaining,
        status="finished",
        reveals=result.reveals,
    )


@app.post("/api/challenges/{seed}/guess", response_model=GuessResponse)
def submit_seeded_guess(
    request: SeededGuessRequest,
    seed: str = Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
) -> GuessResponse:
    anonymous_state = _anonymous_game_state(request.anonymous_state)
    assert anonymous_state is not None
    result = daily_challenge_games.guess_seeded(
        seed=seed,
        guessed_district_id=request.guessed_district_id,
        anonymous_state=anonymous_state,
    )
    return GuessResponse(**result.__dict__)


@app.post("/api/challenges/{seed}/give-up", response_model=GiveUpResponse)
def give_up_seeded_challenge(
    request: SeededGiveUpRequest,
    seed: str = Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
) -> GiveUpResponse:
    anonymous_state = _anonymous_game_state(request.anonymous_state)
    assert anonymous_state is not None
    result = daily_challenge_games.give_up_seeded(seed, anonymous_state)
    return GiveUpResponse(
        budget_remaining=result.budget_remaining,
        status="finished",
        reveals=result.reveals,
    )

if os.path.isdir(STATIC_DIR):
    app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="frontend")
