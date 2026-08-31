"""Seed deterministic local-only example standings for today's Daily Challenge.

Run manually with: ``uv run seed_leaderboard_demo.py`` from ``backend``.
It never modifies an existing account's game for today.
"""

from datetime import UTC, datetime

from database import SessionLocal
from game import INITIAL_BUDGET
from main import challenge_generator, current_challenge_date
from models import Account, GameDailyDistricts, Guess

# username, solved pins, guesses used, total miss distances in metres
EXAMPLES = [
    ("AltonaAce", 5, 5, []),
    ("ElbKartograph", 5, 6, [420.0]),
    ("HanseaticFox", 4, 6, [810.0, 1430.0]),
    ("MoinMara", 3, 8, [300.0, 760.0, 1200.0, 2200.0, 3100.0]),
    ("HarbourHiker", 0, 0, []),
]


def main() -> None:
    challenge_date = current_challenge_date()
    pins = challenge_generator.generate(challenge_date)
    answer_ids = {pin.district.id for pin in pins}

    with SessionLocal() as database:
        for username, solved_count, guesses_used, distances in EXAMPLES:
            account = database.query(Account).filter_by(username=username).one_or_none()
            if account is None:
                account = Account(
                    username=username, password_hash="demo-account-not-for-login"
                )
                database.add(account)
                database.flush()
            exists = (
                database.query(GameDailyDistricts)
                .filter_by(account_id=account.id, challenge_date=challenge_date)
                .first()
            )
            if exists:
                continue
            game = GameDailyDistricts(
                account_id=account.id,
                challenge_date=challenge_date,
                budget_remaining=INITIAL_BUDGET - guesses_used,
                solved_pin_indices=list(range(solved_count)),
                status="finished",
                finished_at=datetime.now(UTC),
            )
            database.add(game)
            database.flush()
            for pin in pins[:solved_count]:
                database.add(
                    Guess(
                        game_id=game.id,
                        guessed_district_id=pin.district.id,
                        was_correct=True,
                        solved_pin_index=pin.index,
                    )
                )
            misses_needed = guesses_used - solved_count
            misses = [
                district
                for district in challenge_generator.catalog.districts
                if district.id not in answer_ids
            ]
            for index in range(misses_needed):
                metres = distances[index] if index < len(distances) else 1000.0
                database.add(
                    Guess(
                        game_id=game.id,
                        guessed_district_id=misses[index].id,
                        was_correct=False,
                        distance_km=round(metres / 1000, 1),
                        distance_meters=metres,
                    )
                )
        database.commit()
    print(f"Seeded demo leaderboard games for {challenge_date}.")


if __name__ == "__main__":
    main()
