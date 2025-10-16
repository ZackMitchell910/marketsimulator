import os
from pathlib import Path

from src.config import env_loader


def clear_cache():
    env_loader.load_env.cache_clear()  # type: ignore[attr-defined]


def test_load_env_explicit_path(tmp_path, monkeypatch):
    clear_cache()
    monkeypatch.delenv("FOO_TEST_ENV", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("FOO_TEST_ENV=hello\n")

    loaded = env_loader.load_env(str(dotenv_path))
    assert loaded is True
    assert os.getenv("FOO_TEST_ENV") == "hello"


def test_load_env_falls_back_to_project_root(tmp_path, monkeypatch):
    clear_cache()
    monkeypatch.delenv("ROOT_ENV_VALUE", raising=False)
    project_root = tmp_path / "proj"
    project_root.mkdir()
    dotenv_path = project_root / ".env"
    dotenv_path.write_text("ROOT_ENV_VALUE=42\n")

    monkeypatch.chdir(project_root)

    loaded = env_loader.load_env()
    assert loaded is True
    assert os.getenv("ROOT_ENV_VALUE") == "42"


def test_load_env_returns_false_when_missing(tmp_path, monkeypatch):
    clear_cache()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MARKETTWIN_DISABLE_PROJECT_DOTENV", "1")
    loaded = env_loader.load_env()
    assert loaded is False
