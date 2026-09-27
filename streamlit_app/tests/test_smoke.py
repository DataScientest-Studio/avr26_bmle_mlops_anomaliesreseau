"""Tests de fumée headless de l'app : aucune page ne lève d'exception,
même quand base et MLflow sont éteints (dégradation propre attendue)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[1]
VIEWS = sorted((APP_DIR / "views").glob("*.py"))


@pytest.fixture(autouse=True)
def _services_off(monkeypatch):
    # Ports volontairement fermés : on teste le chemin « service éteint ».
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "9")


def test_router_runs():
    at = AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=120).run()
    assert not at.exception


@pytest.mark.parametrize("view", VIEWS, ids=[v.stem for v in VIEWS])
def test_view_degrades_cleanly(view):
    at = AppTest.from_file(str(view), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
