from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from game import (
    GENERATION_VERSION,
    INITIAL_BUDGET,
    PIN_COUNT,
    ChallengeGenerator,
    ChallengePin,
    DistrictCatalog,
    GuessResult,
    evaluate_guess,
    reveal,
)
from models import Account, GameDailyDistricts, Guess


class DailyChallengeError(Exception):
    """A Daily Challenge policy failure that an adapter may render."""

    def __init__(self, status_code: int, detail: str, code: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code


@dataclass(frozen=True)
class AnonymousGameState:
    budget_remaining: int
    solved_pin_indices: tuple[int, ...]


@dataclass(frozen=True)
class SubmittedGuess:
    district_id: int


@dataclass(frozen=True)
class DailyChallengeSnapshot:
    challenge_date: date
    pins: list[ChallengePin]
    budget_remaining: int
    solved_pins: list[dict[str, Any]]
    missed_districts: list[dict[str, Any]]
    guess_history: list[dict[str, Any]]
    status: Literal["in_progress", "finished"]
    state_source: Literal["anonymous", "account"]
    finish_reason: Literal["solved", "budget", "gave_up"] | None


@dataclass(frozen=True)
class SeededChallengeSnapshot:
    seed: str
    pins: list[ChallengePin]


@dataclass(frozen=True)
class GiveUpResult:
    budget_remaining: int
    reveals: list[dict[str, Any]]


class DailyChallengeGames:
    """Own Daily Challenge and Shared Map Game lifecycle policy."""

    def __init__(
        self,
        catalog: DistrictCatalog,
        challenge_generator: ChallengeGenerator,
    ) -> None:
        self.catalog = catalog
        self.challenge_generator = challenge_generator

    def daily_snapshot(
        self,
        database: Session,
        account: Account | None,
        challenge_date: date,
    ) -> DailyChallengeSnapshot:
        pins = self.challenge_generator.generate(challenge_date)
        game = (
            self._get_or_create_account_game(database, account.id, challenge_date)
            if account is not None
            else None
        )
        return self._snapshot(challenge_date, pins, game)

    def seeded_snapshot(self, seed: str) -> SeededChallengeSnapshot:
        return SeededChallengeSnapshot(
            seed=seed,
            pins=self.challenge_generator.generate_seeded(seed),
        )

    def adopt_anonymous(
        self,
        database: Session,
        account: Account | None,
        challenge_date: date,
        today: date,
        budget_remaining: int,
        solved_pin_indices: list[int],
        guesses: list[SubmittedGuess],
    ) -> DailyChallengeSnapshot:
        if account is None:
            raise DailyChallengeError(401, "Authentication required")
        if challenge_date != today:
            raise DailyChallengeError(400, "Only today's Daily Challenge can be adopted")
        existing = database.scalar(
            select(GameDailyDistricts.id).where(
                GameDailyDistricts.account_id == account.id,
                GameDailyDistricts.challenge_date == challenge_date,
            )
        )
        if existing is not None:
            raise DailyChallengeError(
                409, "This account already has today's Daily Challenge"
            )

        pins = self.challenge_generator.generate(challenge_date)
        budget = INITIAL_BUDGET
        solved: set[int] = set()
        adopted_guesses: list[tuple[int, GuessResult]] = []
        for submitted in guesses:
            district = self.catalog.by_id.get(submitted.district_id)
            if district is None:
                raise DailyChallengeError(
                    422, "Anonymous result contains an unknown district"
                )
            if budget <= 0 or len(solved) == PIN_COUNT:
                raise DailyChallengeError(
                    422, "Anonymous result contains guesses after completion"
                )
            result = evaluate_guess(pins, district, solved, budget)
            adopted_guesses.append((district.id, result))
            budget = result.budget_remaining
            if result.solved_pin_index is not None:
                solved.add(result.solved_pin_index)

        if budget != budget_remaining or sorted(solved) != sorted(solved_pin_indices):
            raise DailyChallengeError(
                422, "Anonymous result does not match its guesses"
            )

        finish_reason: Literal["solved", "budget", "gave_up"] = (
            "solved" if len(solved) == PIN_COUNT else "budget" if budget == 0 else "gave_up"
        )
        game = GameDailyDistricts(
            account_id=account.id,
            challenge_date=challenge_date,
            budget_remaining=budget,
            solved_pin_indices=sorted(solved),
            status="finished",
            finished_at=datetime.now(UTC),
            finish_reason=finish_reason,
        )
        database.add(game)
        for district_id, result in adopted_guesses:
            database.add(
                Guess(
                    game=game,
                    guessed_district_id=district_id,
                    was_correct=result.correct,
                    solved_pin_index=result.solved_pin_index,
                    distance_km=result.distance_km,
                    distance_meters=result.distance_meters,
                )
            )
        database.commit()
        database.refresh(game)
        return self._snapshot(challenge_date, pins, game)

    def guess_daily(
        self,
        database: Session,
        account: Account | None,
        challenge_date: date,
        today: date,
        guessed_district_id: int,
        anonymous_state: AnonymousGameState | None,
    ) -> GuessResult:
        if challenge_date != today:
            raise DailyChallengeError(
                400, "Only today's Daily Challenge is active"
            )
        pins = self.challenge_generator.generate(today)
        return self._guess(
            database=database,
            account=account,
            challenge_date=today,
            pins=pins,
            guessed_district_id=guessed_district_id,
            anonymous_state=anonymous_state,
        )

    def guess_seeded(
        self,
        seed: str,
        guessed_district_id: int,
        anonymous_state: AnonymousGameState,
    ) -> GuessResult:
        return self._guess(
            database=None,
            account=None,
            challenge_date=None,
            pins=self.challenge_generator.generate_seeded(seed),
            guessed_district_id=guessed_district_id,
            anonymous_state=anonymous_state,
        )

    def give_up_daily(
        self,
        database: Session,
        account: Account | None,
        challenge_date: date,
        today: date,
        anonymous_state: AnonymousGameState | None,
    ) -> GiveUpResult:
        if challenge_date != today:
            raise DailyChallengeError(
                400, "Only today's Daily Challenge is active"
            )

        if account is not None:
            self._get_or_create_account_game(database, account.id, today)
            game = database.scalar(
                select(GameDailyDistricts)
                .where(
                    GameDailyDistricts.account_id == account.id,
                    GameDailyDistricts.challenge_date == today,
                )
                .with_for_update()
            )
            if game is None:
                raise DailyChallengeError(
                    409, "Daily Challenge state is unavailable"
                )
            if game.status == "finished":
                raise DailyChallengeError(
                    409, "Today's Daily Challenge is already finished"
                )
            game.status = "finished"
            game.finished_at = datetime.now(UTC)
            game.finish_reason = "gave_up"
            database.commit()
            budget_remaining = game.budget_remaining
        else:
            if anonymous_state is None:
                raise DailyChallengeError(422, "Anonymous state is required")
            budget_remaining = anonymous_state.budget_remaining

        return GiveUpResult(
            budget_remaining=budget_remaining,
            reveals=[reveal(pin) for pin in self.challenge_generator.generate(today)],
        )

    def give_up_seeded(
        self,
        seed: str,
        anonymous_state: AnonymousGameState,
    ) -> GiveUpResult:
        return GiveUpResult(
            budget_remaining=anonymous_state.budget_remaining,
            reveals=[
                reveal(pin) for pin in self.challenge_generator.generate_seeded(seed)
            ],
        )

    def _guess(
        self,
        database: Session | None,
        account: Account | None,
        challenge_date: date | None,
        pins: list[ChallengePin],
        guessed_district_id: int,
        anonymous_state: AnonymousGameState | None,
    ) -> GuessResult:
        guessed_district = self.catalog.by_id.get(guessed_district_id)
        if guessed_district is None:
            raise DailyChallengeError(404, "District not found")

        game: GameDailyDistricts | None = None
        if account is not None:
            assert database is not None and challenge_date is not None
            self._get_or_create_account_game(database, account.id, challenge_date)
            game = database.scalar(
                select(GameDailyDistricts)
                .where(
                    GameDailyDistricts.account_id == account.id,
                    GameDailyDistricts.challenge_date == challenge_date,
                )
                .with_for_update()
            )
            if game is None:
                raise DailyChallengeError(
                    409, "Daily Challenge state is unavailable"
                )
            if game.status == "finished" or game.budget_remaining <= 0:
                raise DailyChallengeError(
                    409, "Today's Daily Challenge is already finished"
                )
            previous_guess = database.scalar(
                select(Guess.id)
                .where(
                    Guess.game_id == game.id,
                    Guess.guessed_district_id == guessed_district.id,
                )
                .limit(1)
            )
            if previous_guess is not None:
                raise DailyChallengeError(
                    409,
                    "This Stadtteil has already been guessed",
                    code="daily_already_guessed",
                )
            solved_pin_indices = set(game.solved_pin_indices)
            budget_remaining = game.budget_remaining
        else:
            if anonymous_state is None:
                raise DailyChallengeError(422, "Anonymous state is required")
            solved_pin_indices = set(anonymous_state.solved_pin_indices)
            budget_remaining = anonymous_state.budget_remaining

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
                game.finish_reason = (
                    "solved"
                    if len(game.solved_pin_indices) == PIN_COUNT
                    else "budget"
                )
            database.add(
                Guess(
                    game=game,
                    guessed_district_id=guessed_district.id,
                    was_correct=result.correct,
                    solved_pin_index=result.solved_pin_index,
                    distance_km=result.distance_km,
                    distance_meters=result.distance_meters,
                )
            )
            database.commit()

        return result

    def _get_or_create_account_game(
        self,
        database: Session,
        account_id: int,
        challenge_date: date,
    ) -> GameDailyDistricts:
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

    def _snapshot(
        self,
        challenge_date: date,
        pins: list[ChallengePin],
        game: GameDailyDistricts | None,
    ) -> DailyChallengeSnapshot:
        if game is None:
            return DailyChallengeSnapshot(
                challenge_date=challenge_date,
                pins=pins,
                budget_remaining=INITIAL_BUDGET,
                solved_pins=[],
                missed_districts=[],
                guess_history=[],
                status="in_progress",
                state_source="anonymous",
                finish_reason=None,
            )
        return DailyChallengeSnapshot(
            challenge_date=challenge_date,
            pins=pins,
            budget_remaining=game.budget_remaining,
            solved_pins=self._game_reveals(game, pins),
            missed_districts=self._game_missed_districts(game),
            guess_history=self._game_guess_history(game),
            status=game.status,
            state_source="account",
            finish_reason=game.finish_reason,
        )

    @staticmethod
    def _game_reveals(
        game: GameDailyDistricts,
        pins: list[ChallengePin],
    ) -> list[dict[str, Any]]:
        solved_indices = set(game.solved_pin_indices)
        if game.status == "finished":
            return [reveal(pin) for pin in pins]
        return [reveal(pin) for pin in pins if pin.index in solved_indices]

    def _game_missed_districts(
        self,
        game: GameDailyDistricts,
    ) -> list[dict[str, Any]]:
        missed_by_id: dict[int, dict[str, Any]] = {}
        for guess in game.guesses:
            if guess.was_correct:
                continue
            district = self.catalog.by_id.get(guess.guessed_district_id)
            if district is None:
                continue
            missed_by_id[district.id] = {
                "district_id": district.id,
                "district_name": district.name,
                "boundary": district.boundary,
                "distance_km": guess.distance_km,
            }
        return list(missed_by_id.values())

    def _game_guess_history(
        self,
        game: GameDailyDistricts,
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for guess in game.guesses:
            district = self.catalog.by_id.get(guess.guessed_district_id)
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


__all__ = [
    "GENERATION_VERSION",
    "INITIAL_BUDGET",
    "AnonymousGameState",
    "DailyChallengeError",
    "DailyChallengeGames",
    "DailyChallengeSnapshot",
    "GiveUpResult",
    "SeededChallengeSnapshot",
    "SubmittedGuess",
]
