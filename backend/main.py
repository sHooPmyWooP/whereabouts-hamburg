import os
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from auth_routes import get_optional_account
from auth_routes import router as auth_router
from database import engine, get_db
from game import (
    GENERATION_VERSION,
    INITIAL_BUDGET,
    PIN_COUNT,
    ChallengeGenerator,
    DistrictCatalog,
    evaluate_guess,
    reveal,
)
from models import Account, GameDailyDistricts, Guess
from training import create_training_router

load_dotenv()

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"
STATIC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)

catalog = DistrictCatalog.load()
challenge_generator = ChallengeGenerator(catalog)

app = FastAPI(
    title="Hamburg Whereabouts API",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.include_router(auth_router)
app.include_router(create_training_router(catalog))


@app.exception_handler(OperationalError)
def database_unavailable(
    _request: Request, _error: OperationalError
) -> JSONResponse:
    """Return a sanitized, non-cacheable response when PostgreSQL is unavailable."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Account service temporarily unavailable. Please try again."},
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


class ExploreDistrict(DistrictSummary):
    boundary: dict[str, Any]


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
    anonymous_state: AnonymousState


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


def current_challenge_date() -> date:
    """Return the current Daily Challenge date in Hamburg."""
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def get_or_create_account_game(
    database: Session,
    account_id: int,
    challenge_date: date,
) -> GameDailyDistricts:
    """Load or create the Account's single Game for a challenge date."""
    statement = (
        select(GameDailyDistricts)
        .options(selectinload(GameDailyDistricts.guesses))
        .where(
            GameDailyDistricts.account_id == account_id,
            GameDailyDistricts.challenge_date == challenge_date,
        )
    )
    game = database.scalar(statement)
    if game is not None:
        return game

    game = GameDailyDistricts(
        account_id=account_id,
        challenge_date=challenge_date,
        budget_remaining=INITIAL_BUDGET,
        solved_pin_indices=[],
        status="in_progress",
    )
    database.add(game)
    try:
        database.commit()
    except IntegrityError:
        database.rollback()
        existing_game = database.scalar(statement)
        if existing_game is None:
            raise
        return existing_game
    database.refresh(game)
    return game


def game_reveals(
    game: GameDailyDistricts, pins: list[Any]
) -> list[dict[str, Any]]:
    """Reconstruct only the Pin boundaries earned by the Account."""
    solved_indices = set(game.solved_pin_indices)
    if game.status == "finished":
        return [reveal(pin) for pin in pins]
    return [reveal(pin) for pin in pins if pin.index in solved_indices]


def game_missed_districts(game: GameDailyDistricts) -> list[dict[str, Any]]:
    """Reconstruct unique missed District boundaries from accepted Guesses."""
    missed_by_id: dict[int, dict[str, Any]] = {}
    for guess in game.guesses:
        if guess.was_correct:
            continue
        district = catalog.by_id.get(guess.guessed_district_id)
        if district is None:
            continue
        missed_by_id[district.id] = {
            "district_id": district.id,
            "district_name": district.name,
            "boundary": district.boundary,
            "distance_km": guess.distance_km,
        }
    return list(missed_by_id.values())


def game_guess_history(game: GameDailyDistricts) -> list[dict[str, Any]]:
    """Return accepted Account Guesses in submission order."""
    history: list[dict[str, Any]] = []
    for guess in game.guesses:
        district = catalog.by_id.get(guess.guessed_district_id)
        if district is None:
            continue
        history.append(
            {
                "district_id": district.id,
                "district_name": district.name,
                "correct": guess.was_correct,
                "distance_km": guess.distance_km,
                "solved_pin_index": guess.solved_pin_index,
            }
        )
    return history


@app.get("/api/districts", response_model=list[DistrictSummary])
def list_districts() -> list[DistrictSummary]:
    return [
        DistrictSummary(id=district.id, name=district.name, bezirk=district.bezirk)
        for district in catalog.districts
    ]


@app.get("/api/explore/districts", response_model=list[ExploreDistrict])
def explore_districts(response: Response) -> list[ExploreDistrict]:
    """Return public Stadtteil geometry for the interactive explorer."""
    response.headers["Cache-Control"] = "public, max-age=86400"
    return [
        ExploreDistrict(
            id=district.id,
            name=district.name,
            bezirk=district.bezirk,
            boundary=district.boundary,
        )
        for district in catalog.districts
    ]


@app.get("/api/daily", response_model=DailyResponse)
def get_daily(
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> DailyResponse:
    """Return public Pins plus identity-scoped Daily Challenge progress."""
    challenge_date = current_challenge_date()
    pins = challenge_generator.generate(challenge_date)
    game = (
        get_or_create_account_game(database, account.id, challenge_date)
        if account is not None
        else None
    )
    return DailyResponse(
        generation_version=GENERATION_VERSION,
        date=challenge_date,
        pins=[
            PublicPin(index=pin.index, lat=pin.point.y, lng=pin.point.x) for pin in pins
        ],
        initial_budget=INITIAL_BUDGET,
        budget_remaining=game.budget_remaining if game else INITIAL_BUDGET,
        solved_pins=game_reveals(game, pins) if game else [],
        missed_districts=game_missed_districts(game) if game else [],
        guess_history=game_guess_history(game) if game else [],
        status=game.status if game else "in_progress",
        state_source="account" if game else "anonymous",
    )


@app.get("/api/challenges/{seed}", response_model=SeededChallengeResponse)
def get_seeded_challenge(
    seed: str = Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
) -> SeededChallengeResponse:
    pins = challenge_generator.generate_seeded(seed)
    return SeededChallengeResponse(
        generation_version=GENERATION_VERSION,
        seed=seed,
        pins=[
            PublicPin(index=pin.index, lat=pin.point.y, lng=pin.point.x) for pin in pins
        ],
        initial_budget=INITIAL_BUDGET,
        budget_remaining=INITIAL_BUDGET,
        solved_pins=[],
        status="in_progress",
    )


@app.post("/api/daily/guess", response_model=GuessResponse)
def submit_guess(
    request: GuessRequest,
    database: Annotated[Session, Depends(get_db)],
    account: Annotated[Account | None, Depends(get_optional_account)],
) -> GuessResponse:
    """Evaluate a Guess using Account state or validated anonymous state."""
    today = current_challenge_date()
    if request.challenge_date != today:
        raise HTTPException(status_code=400, detail="Only today's Daily Challenge is active")

    guessed_district = catalog.by_id.get(request.guessed_district_id)
    if guessed_district is None:
        raise HTTPException(status_code=404, detail="District not found")

    pins = challenge_generator.generate(today)
    if account is not None:
        get_or_create_account_game(database, account.id, today)
        game = database.scalar(
            select(GameDailyDistricts)
            .where(
                GameDailyDistricts.account_id == account.id,
                GameDailyDistricts.challenge_date == today,
            )
            .with_for_update()
        )
        if game is None:
            raise HTTPException(status_code=409, detail="Daily Challenge state is unavailable")
        if game.status == "finished" or game.budget_remaining <= 0:
            raise HTTPException(status_code=409, detail="Today's Daily Challenge is already finished")
        previous_guess = database.scalar(
            select(Guess.id)
            .where(
                Guess.game_id == game.id,
                Guess.guessed_district_id == guessed_district.id,
            )
            .limit(1)
        )
        if previous_guess is not None:
            raise HTTPException(status_code=409, detail="This Stadtteil has already been guessed")
        solved_pin_indices = set(game.solved_pin_indices)
        budget_remaining = game.budget_remaining
    else:
        if request.anonymous_state is None:
            raise HTTPException(status_code=422, detail="Anonymous state is required")
        game = None
        solved_pin_indices = set(request.anonymous_state.solved_pin_indices)
        budget_remaining = request.anonymous_state.budget_remaining

    result = evaluate_guess(
        pins=pins,
        guessed_district=guessed_district,
        solved_pin_indices=solved_pin_indices,
        budget_remaining=budget_remaining,
    )
    if game is not None:
        if result.solved_pin_index is not None:
            game.solved_pin_indices = sorted(
                {*game.solved_pin_indices, result.solved_pin_index}
            )
        game.budget_remaining = result.budget_remaining
        game.status = result.status
        if result.status == "finished":
            game.finished_at = datetime.now(UTC)
        database.add(
            Guess(
                game=game,
                guessed_district_id=guessed_district.id,
                was_correct=result.correct,
                solved_pin_index=result.solved_pin_index,
                distance_km=result.distance_km,
            )
        )
        database.commit()
    return GuessResponse(**result.__dict__)


@app.post("/api/daily/give-up", response_model=GiveUpResponse)
def give_up_daily(request: DailyGiveUpRequest) -> GiveUpResponse:
    today = current_challenge_date()
    if request.challenge_date != today:
        raise HTTPException(status_code=400, detail="Only today's Daily Challenge is active")

    return GiveUpResponse(
        budget_remaining=request.anonymous_state.budget_remaining,
        status="finished",
        reveals=[reveal(pin) for pin in challenge_generator.generate(today)],
    )


@app.post("/api/challenges/{seed}/guess", response_model=GuessResponse)
def submit_seeded_guess(
    request: SeededGuessRequest,
    seed: str = Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
) -> GuessResponse:
    guessed_district = catalog.by_id.get(request.guessed_district_id)
    if guessed_district is None:
        raise HTTPException(status_code=404, detail="District not found")

    pins = challenge_generator.generate_seeded(seed)
    result = evaluate_guess(
        pins=pins,
        guessed_district=guessed_district,
        solved_pin_indices=set(request.anonymous_state.solved_pin_indices),
        budget_remaining=request.anonymous_state.budget_remaining,
    )
    return GuessResponse(**result.__dict__)


@app.post("/api/challenges/{seed}/give-up", response_model=GiveUpResponse)
def give_up_seeded_challenge(
    request: SeededGiveUpRequest,
    seed: str = Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
) -> GiveUpResponse:
    return GiveUpResponse(
        budget_remaining=request.anonymous_state.budget_remaining,
        status="finished",
        reveals=[reveal(pin) for pin in challenge_generator.generate_seeded(seed)],
    )

if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
