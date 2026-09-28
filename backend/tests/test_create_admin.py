import pytest

from app import create_admin
from app.storage import connect, hash_password, initialize_database


@pytest.mark.parametrize("role", ["ADMINISTRATOR", "VERIFIER"])
def test_setup_rerun_never_changes_an_existing_account(tmp_path, monkeypatch, role):
    path = tmp_path / "intrac.db"
    monkeypatch.setenv("INTRAC_DB_PATH", str(path))
    monkeypatch.setattr("sys.argv", ["create_admin", "--first-name", "System", "--last-name", "Admin", "--username", " ADMIN ", "--if-missing"])
    initialize_database(path)
    encoded = hash_password("existing-password")
    with connect(path) as connection:
        connection.execute("INSERT INTO users (first_name, last_name, username, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                           ("Existing", "User", "admin", encoded, role))

    def unexpected_prompt(*args):
        pytest.fail("An existing account must be checked before asking for a new password")

    monkeypatch.setattr(create_admin.getpass, "getpass", unexpected_prompt)
    if role == "VERIFIER":
        with pytest.raises(SystemExit) as error:
            create_admin.main()
        assert error.value.code == 2
    else:
        create_admin.main()
    with connect(path) as connection:
        row = connection.execute("SELECT * FROM users").fetchone()
    assert row["first_name"] == "Existing"
    assert row["password_hash"] == encoded
    assert row["role"] == role


def test_setup_creates_an_administrator_in_a_fresh_database(tmp_path, monkeypatch):
    path = tmp_path / "intrac.db"
    monkeypatch.setenv("INTRAC_DB_PATH", str(path))
    monkeypatch.setenv("INTRAC_ADMIN_PASSWORD", "initial-test-password")
    monkeypatch.setattr("sys.argv", ["create_admin", "--first-name", "System", "--last-name", "Admin", "--username", "admin", "--if-missing"])
    create_admin.main()
    create_admin.main()
    with connect(path) as connection:
        rows = connection.execute("SELECT username, role FROM users").fetchall()
    assert [tuple(row) for row in rows] == [("admin", "ADMINISTRATOR")]
