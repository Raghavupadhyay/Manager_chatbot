"""Shared fixtures — every test runs against an isolated temp data dir."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("GOOGLE_API_KEY", "")  # CI path: no real key


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Point settings at a temp dir so tests never touch ./data, and force the
    offline path — .env may hold a real GOOGLE_API_KEY."""
    from ops_copilot import config

    old_dir = config.settings.data_dir
    old_key = config.settings.google_api_key
    old_judge = config.settings.guard_llm_judge
    old_shifts = config.settings.booking_max_date_shifts
    old_max_chars = config.settings.goal_max_chars
    config.settings.data_dir = tmp_path / "data"
    config.settings.google_api_key = ""
    config.settings.guard_llm_judge = False
    config.settings.ensure_dirs()
    yield config.settings
    config.settings.data_dir = old_dir
    config.settings.google_api_key = old_key
    config.settings.guard_llm_judge = old_judge
    config.settings.booking_max_date_shifts = old_shifts
    config.settings.goal_max_chars = old_max_chars


@pytest.fixture(autouse=True)
def reset_metrics():
    from ops_copilot.observability.metrics import metrics

    yield
    metrics.reset()


@pytest.fixture()
def seeded_db(isolated_settings):
    """Fresh migrated+seeded domain DB; returns its path."""
    from ops_copilot.db.init import init_fresh

    path = isolated_settings.app_db_path
    init_fresh(path)
    return path
