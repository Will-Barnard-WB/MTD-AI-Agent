"""Smoke-test the Streamlit console in-process (no browser) via AppTest.

Runs the actual script and every page, asserting no exception is raised. Button-gated
actions (subprocess test runs, triggering a pipeline) are not clicked here — this proves
the UI renders and wires up cleanly.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "dashboard" / "app.py")

PAGES = ["Runs", "Run a return", "Playground", "Tests & Experiments",
         "Monitoring", "Command catalog"]


def test_app_default_page_renders():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception


@pytest.mark.parametrize("page", PAGES)
def test_each_page_renders(page):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, f"{page}: {at.exception}"
