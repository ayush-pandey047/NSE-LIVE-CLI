import requests

BASE_URL = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

API_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

session = requests.Session()
session.headers.update(HEADERS)
try:
    res1 = session.get(BASE_URL, timeout=10)
    print("Homepage status:", res1.status_code)
    print("Cookies:", session.cookies.get_dict())
    
    session.headers.update(API_HEADERS)
    res2 = session.get(BASE_URL + "/api/quote-equity?symbol=RELIANCE", timeout=10)
    print("API status:", res2.status_code)
    print("API response:", res2.text[:200])
except Exception as e:
    print("Error:", e)
