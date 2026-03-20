"""Playwright E2E tests for Aegis backoffice."""
import os
import time
import pytest
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://localhost:18501"
SCREENSHOT_DIR = "tests/screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


def _wait_streamlit(page, url, timeout=20000):
    page.goto(url, timeout=timeout)
    page.wait_for_load_state("networkidle", timeout=timeout)
    time.sleep(2)  # Extra wait for Streamlit hydration


def _no_error(page):
    """Check no Streamlit error boxes visible."""
    errors = page.locator(".stException, .stError").count()
    return errors == 0


class TestBackofficePages:
    def test_main_page_loads(self, page):
        _wait_streamlit(page, BASE_URL)
        page.screenshot(path=f"{SCREENSHOT_DIR}/00_main.png")
        assert page.locator("h1").count() > 0 or page.locator(".stApp").count() > 0

    def test_live_dashboard(self, page):
        _wait_streamlit(page, f"{BASE_URL}/01_live_dashboard")
        page.screenshot(path=f"{SCREENSHOT_DIR}/01_live_dashboard.png")
        assert _no_error(page), "Live Dashboard has errors"

    def test_decision_log(self, page):
        _wait_streamlit(page, f"{BASE_URL}/02_decision_log")
        page.screenshot(path=f"{SCREENSHOT_DIR}/02_decision_log.png")
        assert _no_error(page), "Decision Log has errors"

    def test_trade_journal(self, page):
        _wait_streamlit(page, f"{BASE_URL}/03_trade_journal")
        page.screenshot(path=f"{SCREENSHOT_DIR}/03_trade_journal.png")
        assert _no_error(page), "Trade Journal has errors"

    def test_pnl_analytics(self, page):
        _wait_streamlit(page, f"{BASE_URL}/04_pnl_analytics")
        page.screenshot(path=f"{SCREENSHOT_DIR}/04_pnl_analytics.png")
        assert _no_error(page), "PnL Analytics has errors"

    def test_model_monitor(self, page):
        _wait_streamlit(page, f"{BASE_URL}/05_model_monitor")
        page.screenshot(path=f"{SCREENSHOT_DIR}/05_model_monitor.png")
        assert _no_error(page), "Model Monitor has errors"

    def test_risk_dashboard(self, page):
        _wait_streamlit(page, f"{BASE_URL}/06_risk_dashboard")
        page.screenshot(path=f"{SCREENSHOT_DIR}/06_risk_dashboard.png")
        assert _no_error(page), "Risk Dashboard has errors"

    def test_backtest_viewer(self, page):
        _wait_streamlit(page, f"{BASE_URL}/07_backtest_viewer")
        page.screenshot(path=f"{SCREENSHOT_DIR}/07_backtest_viewer.png")
        assert _no_error(page), "Backtest Viewer has errors"

    def test_system_ops(self, page):
        _wait_streamlit(page, f"{BASE_URL}/08_system_ops")
        page.screenshot(path=f"{SCREENSHOT_DIR}/08_system_ops.png")
        assert _no_error(page), "System Ops has errors"
