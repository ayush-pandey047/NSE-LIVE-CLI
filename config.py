BASE_URL = "https://www.nseindia.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Headers used for XHR/API calls (after homepage visit)
API_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer": "https://www.nseindia.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
    "DNT": "1",
}

# ── Endpoints ─────────────────────────────────────────────────
HOMEPAGE_URL   = f"{BASE_URL}/"
QUOTE_EQUITY   = f"{BASE_URL}/api/quote-equity"   # ?symbol=<SYMBOL>
MARKET_STATUS  = f"{BASE_URL}/api/marketStatus"   # future use

# ── Defaults ─────────────────────────────────────────────────
DEFAULT_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "WIPRO"]
REFRESH_INTERVAL = 3          # seconds between live updates
REQUEST_TIMEOUT  = 10         # seconds before request gives up
SESSION_REFRESH  = 300        # re-init session every N seconds (5 min)

# ── Display ───────────────────────────────────────────────────
DASHBOARD_TITLE = "NSE Live Stock Dashboard"
TABLE_WIDTH     = 72
COL_WIDTHS = {
    "symbol":   12,
    "price":    12,
    "change":   10,
    "pct":      10,
    "high":     10,
    "low":      10,
}

# ── Future: CSV Logging ───────────────────────────────────────
ENABLE_CSV_LOG  = False        # flip to True to enable
CSV_LOG_PATH    = "nse_log.csv"

# ── Future: Alerts ───────────────────────────────────────────
ALERT_THRESHOLDS: dict[str, float] = {}
# example: {"RELIANCE": 2.0}  → alert when |%change| > 2 %


# config.py
# ─────────────────────────────────────────────────────────────
# Central configuration for the NSE Live Dashboard CLI tool.
# All tuneable constants live here — no magic numbers elsewhere.
# ─────────────────────────────────────────────────────────────

# ── Network ──────────────────────────────────────────────────