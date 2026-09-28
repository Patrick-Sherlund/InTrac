import argparse
import getpass
import os
import sqlite3

from pydantic import ValidationError

from .main import Role, UserCreate
from .storage import connect, database_path, initialize_database, insert_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an InTrac administrator.")
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--if-missing", action="store_true", help="Skip an existing administrator without changing its password.")
    arguments = parser.parse_args()
    path = database_path()
    initialize_database(path)
    if arguments.if_missing:
        with connect(path) as connection:
            existing = connection.execute("SELECT role FROM users WHERE username = ?", (arguments.username.strip(),)).fetchone()
        if existing is not None:
            if existing["role"] != Role.ADMINISTRATOR:
                parser.error("That username belongs to a verifier. Choose another administrator username.")
            print(f"Administrator '{arguments.username.strip()}' already exists. No account was changed.")
            return
    password = os.environ.get("INTRAC_ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass("Administrator password (12–128 characters): ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("Passwords do not match.")
    try:
        user = UserCreate(
            first_name=arguments.first_name, last_name=arguments.last_name, username=arguments.username,
            password=password, role=Role.ADMINISTRATOR
        )
    except ValidationError as error:
        parser.error("; ".join(f"{item['loc'][-1]}: {item['msg']}" for item in error.errors()))
    try:
        insert_user(path, **user.model_dump())
    except sqlite3.IntegrityError:
        parser.error("That username is already in use. No existing account was changed.")
    print(f"Created administrator '{user.username}'.")


if __name__ == "__main__":
    main()
