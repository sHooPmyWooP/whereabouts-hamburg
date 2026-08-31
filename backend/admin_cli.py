from __future__ import annotations

import argparse

from sqlalchemy import func, select

from database import SessionLocal
from models import Account, AnalyticsEvent, VisitorAccountLink


def find_account(username: str) -> Account:
    with SessionLocal() as database:
        account = database.scalar(
            select(Account).where(func.lower(Account.username) == username.lower())
        )
        if account is None:
            raise SystemExit(f"Account not found: {username}")
        database.expunge(account)
        return account


def set_admin(username: str, enabled: bool) -> None:
    with SessionLocal() as database:
        account = database.scalar(
            select(Account).where(func.lower(Account.username) == username.lower())
        )
        if account is None:
            raise SystemExit(f"Account not found: {username}")
        account.is_admin = enabled
        database.commit()
        print(f"{account.username}: admin={enabled}")


def delete_account(username: str, confirmed: bool) -> None:
    if not confirmed:
        raise SystemExit("Account deletion requires --yes")
    with SessionLocal() as database:
        account = database.scalar(
            select(Account).where(func.lower(Account.username) == username.lower())
        )
        if account is None:
            raise SystemExit(f"Account not found: {username}")
        visitor_ids = list(
            database.scalars(
                select(VisitorAccountLink.visitor_id).where(
                    VisitorAccountLink.account_id == account.id
                )
            )
        )
        if visitor_ids:
            database.query(AnalyticsEvent).filter(
                AnalyticsEvent.visitor_id.in_(visitor_ids)
            ).delete(synchronize_session=False)
        database.delete(account)
        database.commit()
        print(f"Deleted Account {username} and its linked raw analytics")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hamburg Whereabouts administration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("promote", "demote"):
        command = subcommands.add_parser(name)
        command.add_argument("username")
    delete_command = subcommands.add_parser("delete-account")
    delete_command.add_argument("username")
    delete_command.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if args.command == "promote":
        set_admin(args.username, True)
    elif args.command == "demote":
        set_admin(args.username, False)
    else:
        delete_account(args.username, args.yes)


if __name__ == "__main__":
    main()
