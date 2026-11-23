"""Tests for the configurable CORS allow-list.

allow_origins was hardcoded to ["http://localhost:5173"] in main.py --
the one thing that made this app unreachable from any machine but the
one running it. The app itself has always been multi-user capable (JWT
+ roles, server-side ownership checks, Postgres concurrency); this was
purely a hosting constraint baked into source.

Worth testing, not eyeballing, because the failure mode is silent: a
mis-split origin doesn't raise, it just makes the browser refuse every
request with no server-side error to read."""

from app.infra.config import Settings
from app.main import app


def _settings(**kwargs) -> Settings:
    """`_env_file=None` disables .env loading for these instances.

    Without it these assertions read whatever is in the developer's
    backend/.env, so adding a second origin there to reach the app at
    127.0.0.1 turned the default-value test red — a failure about local
    configuration dressed up as a failure about code. Same ambient-config
    trap as the feature flags pinned in conftest.py; the fix is the same
    in spirit: a test about a default must construct the default.
    """
    return Settings(
        _env_file=None, database_url="postgresql+psycopg://x/y", jwt_secret_key="z", **kwargs
    )


def test_cors_origins_defaults_to_the_local_vite_dev_server(monkeypatch):
    """Both sources of ambient configuration have to go, not just one:
    `_env_file=None` stops the .env file being read, and this removes the
    OS environment variable, which outranks the file in pydantic-settings
    and is what docker-compose injects. A test asserting a default must
    own every input to that default."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert _settings().cors_origin_list == ["http://localhost:5173"]


def test_cors_origins_splits_a_comma_separated_list_and_trims_whitespace():
    parsed = _settings(cors_origins="http://localhost:5173, http://192.168.1.42:5173")
    assert parsed.cors_origin_list == ["http://localhost:5173", "http://192.168.1.42:5173"]


def test_cors_origins_drops_empty_entries_from_a_trailing_comma():
    """A trailing comma is the most likely hand-editing slip in a .env,
    and an empty-string origin would never match anything."""
    assert _settings(cors_origins="http://localhost:5173,,").cors_origin_list == [
        "http://localhost:5173"
    ]


def test_the_app_never_serves_a_wildcard_origin():
    """`allow_credentials=True` with `allow_origins=["*"]` is rejected by
    browsers outright, and this API carries bearer tokens — so the
    allow-list must stay an allow-list however it is configured."""
    cors = next(m for m in app.user_middleware if "CORSMiddleware" in str(m.cls))
    assert "*" not in cors.kwargs["allow_origins"]
    assert cors.kwargs["allow_credentials"] is True
