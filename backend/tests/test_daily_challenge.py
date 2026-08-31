from conftest import TestSession

from daily_challenge import AnonymousGameState
from main import catalog, current_challenge_date, daily_challenge_games
from models import Account


def _missed_district(challenge_date):
    answer_ids = {
        pin.district.id
        for pin in daily_challenge_games.challenge_generator.generate(challenge_date)
    }
    return next(
        district for district in catalog.districts if district.id not in answer_ids
    )


def test_in_progress_miss_exposes_district_boundary() -> None:
    challenge_date = current_challenge_date()
    miss = _missed_district(challenge_date)

    with TestSession() as database:
        result = daily_challenge_games.guess_daily(
            database=database,
            account=None,
            challenge_date=challenge_date,
            today=challenge_date,
            guessed_district_id=miss.id,
            anonymous_state=AnonymousGameState(
                budget_remaining=10,
                solved_pin_indices=(),
            ),
        )

    assert result.status == "in_progress"
    assert result.correct is False
    assert result.distance_km is not None
    assert result.missed_district is not None
    assert result.missed_district["district_id"] == miss.id
    assert result.missed_district["boundary"]["type"] == "MultiPolygon"
    assert result.reveals == []


def test_seeded_in_progress_miss_exposes_district_boundary() -> None:
    seed = "boundary-test"
    answer_ids = {
        pin.district.id
        for pin in daily_challenge_games.challenge_generator.generate_seeded(seed)
    }
    miss = next(
        district for district in catalog.districts if district.id not in answer_ids
    )

    result = daily_challenge_games.guess_seeded(
        seed=seed,
        guessed_district_id=miss.id,
        anonymous_state=AnonymousGameState(
            budget_remaining=10,
            solved_pin_indices=(),
        ),
    )

    assert result.status == "in_progress"
    assert result.missed_district is not None
    assert result.missed_district["district_id"] == miss.id
    assert result.missed_district["boundary"]["type"] == "MultiPolygon"


def test_finishing_miss_may_reveal_district_geometry() -> None:
    challenge_date = current_challenge_date()
    miss = _missed_district(challenge_date)

    with TestSession() as database:
        result = daily_challenge_games.guess_daily(
            database=database,
            account=None,
            challenge_date=challenge_date,
            today=challenge_date,
            guessed_district_id=miss.id,
            anonymous_state=AnonymousGameState(
                budget_remaining=1,
                solved_pin_indices=(),
            ),
        )

    assert result.status == "finished"
    assert result.missed_district is not None
    assert result.missed_district["boundary"]["type"] == "MultiPolygon"
    assert len(result.reveals) == 5


def test_account_snapshot_includes_missed_geometry_during_game() -> None:
    challenge_date = current_challenge_date()
    miss = _missed_district(challenge_date)

    with TestSession() as database:
        account = Account(
            username="PolicyPlayer",
            password_hash="not-used-by-this-test",
        )
        database.add(account)
        database.commit()
        database.refresh(account)

        daily_challenge_games.guess_daily(
            database=database,
            account=account,
            challenge_date=challenge_date,
            today=challenge_date,
            guessed_district_id=miss.id,
            anonymous_state=None,
        )
        active = daily_challenge_games.daily_snapshot(
            database, account, challenge_date
        )

        assert active.status == "in_progress"
        assert active.missed_districts[0]["district_id"] == miss.id
        assert active.missed_districts[0]["boundary"]["type"] == "MultiPolygon"
        assert len(active.guess_history) == 1

        daily_challenge_games.give_up_daily(
            database=database,
            account=account,
            challenge_date=challenge_date,
            today=challenge_date,
            anonymous_state=None,
        )
        finished = daily_challenge_games.daily_snapshot(
            database, account, challenge_date
        )

    assert finished.status == "finished"
    assert len(finished.solved_pins) == 5
    assert finished.missed_districts[0]["district_id"] == miss.id
    assert finished.missed_districts[0]["boundary"]["type"] == "MultiPolygon"
