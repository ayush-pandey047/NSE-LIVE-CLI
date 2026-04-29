# nse_session.py
# ─────────────────────────────────────────────────────────────
# Manages a persistent requests.Session that:
#   1. Visits the NSE homepage first to obtain cookies/tokens.
#   2. Reuses those cookies on every subsequent API call.
#   3. Auto-refreshes the session after SESSION_REFRESH seconds.
# ─────────────────────────────────────────────────────────────

import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    HEADERS,
    API_HEADERS,
    HOMEPAGE_URL,
    REQUEST_TIMEOUT,
    SESSION_REFRESH,
)

logger = logging.getLogger(__name__)


def _build_retry_adapter() -> HTTPAdapter:
    """
    Attach an HTTPAdapter with automatic retries for transient errors.
    Retries on 429 (rate-limit) and 5xx server errors with back-off.
    """
    retry_strategy = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    return HTTPAdapter(max_retries=retry_strategy)


class NSESession:
    """
    A thin wrapper around requests.Session tuned for NSE.

    Usage
    -----
        session = NSESession()
        response = session.get("https://www.nseindia.com/api/quote-equity",
                               params={"symbol": "TCS"})
    """

    def __init__(self) -> None:
        self._session: requests.Session | None = None
        self._last_init: float = 0.0
        self._init_session()

    # ── Public ────────────────────────────────────────────────

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Perform a GET request, auto-refreshing the session if stale.
        Merges API_HEADERS by default; caller can override via headers=.
        """
        self._refresh_if_stale()
        kwargs.setdefault("headers", API_HEADERS)
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        try:
            response = self._session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response else "?"
            logger.warning("HTTP %s for %s — forcing session refresh.", status, url)
            self._init_session()          # re-warm cookies
            raise
        except requests.exceptions.RequestException as exc:
            logger.error("Request failed: %s", exc)
            raise

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    # ── Private ───────────────────────────────────────────────

    def _init_session(self) -> None:
        """
        Create a fresh session, mount retry logic, visit NSE homepage
        to populate cookies, then switch to API headers.
        """
        if self._session:
            self._session.close()

        session = requests.Session()
        adapter = _build_retry_adapter()
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Step 1 – visit homepage with browser-like headers
        session.headers.update(HEADERS)
        try:
            resp = session.get(HOMEPAGE_URL, timeout=REQUEST_TIMEOUT)
            logger.debug(
                "Homepage visit: HTTP %s | cookies: %s",
                resp.status_code,
                list(session.cookies.keys()),
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("Homepage pre-warm failed: %s — continuing anyway.", exc)

        # Step 2 – switch to XHR/API headers for subsequent calls
        session.headers.update(API_HEADERS)

        self._session = session
        self._last_init = time.monotonic()
        logger.info("NSE session initialised.")

    def _refresh_if_stale(self) -> None:
        """Re-initialise the session if it has exceeded SESSION_REFRESH seconds."""
        age = time.monotonic() - self._last_init
        if age >= SESSION_REFRESH:
            logger.info("Session stale (%.0fs) — refreshing.", age)
            self._init_session()

    # ── Context-manager support ───────────────────────────────

    def __enter__(self) -> "NSESession":
        return self

    def __exit__(self, *_) -> None:
        self.close()