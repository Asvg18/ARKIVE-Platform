"""The database address is normalised to the psycopg driver on load."""

import pytest

from app.infra.config import Settings


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ('"postgresql://u:p@host/db"', "postgresql+psycopg://u:p@host/db"),
        ("  postgresql://u:p@host/db\n", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_the_address_names_the_psycopg_driver(given, expected):
    settings = Settings(_env_file=None, database_url=given, jwt_secret_key="x")

    assert settings.database_url == expected
