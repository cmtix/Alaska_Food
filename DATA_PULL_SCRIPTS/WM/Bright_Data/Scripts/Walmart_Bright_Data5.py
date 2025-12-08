# walmart_scraper_full.py
# End-to-end: Bright Data CA + AK-targeted proxy + Requests -> Playwright fallback

# --- Imports -------------------------------------------------------------------
import os
import json
import time
import random
import string
import pathlib
import shutil
import certifi
import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import runpy
import sys, subprocess
import playwright  # ensure package is installed

# --- Paths / SSL (Bright Data CA + certifi combined bundle) --------------------
BRIGHTDATA_CA = r"C:/Users/vlcollier/BRIGHT_DATA/brightdata_proxy_ca/SSL/brightdata.crt"
assert os.path.exists(BRIGHTDATA_CA), "Bright Data CA file not found"

COMBINED = str(pathlib.Path(BRIGHTDATA_CA).with_name("combined-ca-bundle.crt"))
# Build (or rebuild) the combined bundle every run (cheap + deterministic)
shutil.copyfile(certifi.where(), COMBINED)
with open(COMBINED, "ab") as out, open(BRIGHTDATA_CA, "rb") as extra:
    out.write(b"\n")
    out.write(extra.read())

# Make Requests (and curl) trust the combined bundle
os.environ["REQUESTS_CA_BUNDLE"] = COMBINED
os.environ["CURL_CA_BUNDLE"] = COMBINED

# --- Proxy (Alaska targeting + sticky sessions) ---------------------------------
BRD_USER_BASE = "brd-customer-hl_a394e9a7-zone-residential_proxy1-country-us-state-ak"
BRD_PASS      = "n51uj6o186v8"
BRD_HOST      = "brd.superproxy.io"
BRD_PORT      = 33335

def _rand_session(n=10):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

def build_proxies(session_id: str):
    user  = f"{BRD_USER_BASE}-session-{session_id}"
    proxy = f"http://{user}:{BRD_PASS}@{BRD_HOST}:{BRD_PORT}"
    return {"http": proxy, "https": proxy}

# One sticky session id reused for the *entire* Playwright run (reduces fingerprint churn)
GLOBAL_PW_SESSION_ID = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12))

# --- Config --------------------------------------------------------------------
SEARCH_LIST_FILE = "WM_search_list_Aug 2025.txt"
DEFAULT_TIMEOUT  = 30

# --- Session factories ----------------------------------------------------------
def make_session_for_smoke() -> requests.Session:
    """Simple session (no sticky) for Bright Data 'geo' smoke test."""
    user  = BRD_USER_BASE  # no -session here, just to test TLS chain via proxy
    proxy = f"http://{user}:{BRD_PASS}@{BRD_HOST}:{BRD_PORT}"
    s = requests.Session()
    s.proxies.update({"http": proxy, "https": proxy})
    s.verify = COMBINED
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    })
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

def make_session_sticky() -> requests.Session:
    """Requests session using a fresh sticky session id (rotated per call)."""
    sid = _rand_session()
    s = requests.Session()
    s.proxies.update(build_proxies(sid))
    s.verify = COMBINED
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.walmart.com/",
    })
    # Let *us* handle 502s/blocks (we’ll rotate session manually)
    retries = Retry(total=0)
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

# --- Utilities -----------------------------------------------------------------
def proxy_smoke_test():
    s = make_session_for_smoke()
    r = s.get("https://geo.brdtest.com/mygeo.json", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    print("Proxy OK:", r.status_code, r.text.strip()[:200])

def load_search_lists(path: str):
    data = runpy.run_path(path)
    items = data["item_list"]
    zips  = data["zip_codes"]

    df_items = pd.DataFrame(items, columns=["item"])
    df_zips  = pd.DataFrame(zips,  columns=["zip_code"])

    keywords = df_items["item"].tolist()
    zip_list = df_zips["zip_code"].tolist()
    return df_items, df_zips, keywords, zip_list

# --- Walmart parsers ------------------------------------------------------------
def _safe_json_loads(s: str):
    """Accept either raw JSON text or an HTML string containing __NEXT_DATA__."""
    s = s.strip() if isinstance(s, str) else s
    if isinstance(s, str) and s.startswith("{") and s.endswith("}"):
        # Raw JSON text
        return json.loads(s)

    # Otherwise treat as HTML and extract __NEXT_DATA__
    soup = BeautifulSoup(s, "html.parser")
    tag  = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag or not tag.string:
        return None
    return json.loads(tag.string)

def parse_json_products(payload: str | dict):
    """
    Parse products from Walmart's __NEXT_DATA__ JSON (preferred).
    Accepts either the raw HTML (containing __NEXT_DATA__) or a JSON string/dict.
    Defensive against shape changes and non-dict items.
    """
    if isinstance(payload, (str, bytes)):
        try:
            data = _safe_json_loads(payload if isinstance(payload, str) else payload.decode("utf-8", "ignore"))
            if data is None:
                return []
        except Exception as e:
            print("[WARN] __NEXT_DATA__ load failed:", e)
            return []
    elif isinstance(payload, dict):
        data = payload
    else:
        return []

    def g(obj, *keys, default=None):
        cur = obj
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return default if cur is None else cur

    items_out = []

    # Prefer pageProps.initialData.* paths, but be defensive
    candidates = []
    ini = g(data, "props", "pageProps", "initialData", default={})
    if isinstance(ini, dict):
        candidates.append(ini)
    elif isinstance(ini, list):
        candidates += [x for x in ini if isinstance(x, dict)]

    stacks_all = []
    for cand in candidates:
        sr = cand.get("searchResult") if isinstance(cand, dict) else None
        if isinstance(sr, dict):
            stacks = sr.get("itemStacks")
            if isinstance(stacks, list):
                stacks_all.extend(stacks)

    # alt older path
    if not stacks_all:
        alt = g(data, "props", "pageProps", "ssr", "data", "searchResult", "itemStacks", default=[])
        if isinstance(alt, list):
            stacks_all.extend(alt)

    for stack in stacks_all:
        if isinstance(stack, dict):
            items = stack.get("items")
            if not isinstance(items, list):
                continue
        elif isinstance(stack, list):
            items = stack
        else:
            continue

        for it in items:
            if not isinstance(it, dict):
                continue

            title      = it.get("title")
            us_item_id = it.get("usItemId") or it.get("usItemID")
            upc        = it.get("upc")

            price_display = (
                (it.get("price") or {}).get("priceDisplay")
                or g(it, "priceInfo", "currentPrice", "priceString")
                or g(it, "priceInfo", "currentPrice", "price")
                or g(it, "primaryOffer", "offerPrice")
            )

            desc = it.get("shortDescription") or it.get("description")

            weight_or_size = None
            tl = title.lower() if isinstance(title, str) else ""
            for tok in ["fl oz", "oz", "lb", "lbs", "pound", "g", "kg", "ct", "pack"]:
                if tok in tl:
                    weight_or_size = tok
                    break

            items_out.append({
                "product_name": title,
                "product_description": desc,
                "product_price": price_display,
                "product_weight_or_size": weight_or_size,
                "upc": upc,
                "product_id": us_item_id,
            })

    return items_out

def parse_html_products(html: str):
    """Fallback: scrape some basics from the DOM (fragile)."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("[data-automation-id='productTile']"):
        name_el  = card.select_one("a span")
        price_el = card.select_one("span[data-automation-id='product-price']")
        results.append({
            "product_name": name_el.get_text(strip=True) if name_el else None,
            "product_description": None,
            "product_price": price_el.get_text(strip=True) if price_el else None,
            "product_weight_or_size": None,
            "upc": None,
            "product_id": None,
        })
    return results

# --- Requests path (fast, but can be blocked) ---------------------------------
class Blocked(Exception):
    pass

def fetch_with_requests(zipcode: int, keyword: str, max_attempts: int = 2):
    """
    Fetch a search page using plain requests + Bright Data sticky proxy.
    Rotate sticky session on block/502. Return parsed products (list).
    """
    url    = "https://www.walmart.com/search"
    params = {"q": keyword, "postalCode": zipcode}

    last_err = None
    for attempt in range(1, max_attempts + 1):
        s = make_session_sticky()
        try:
            r = s.get(url, params=params, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
            # Detect Walmart block patterns
            if "/blocked?" in r.url or r.status_code in (403, 429, 503):
                raise Blocked(f"blocked ({r.status_code}) url={r.url}")
            if r.status_code == 502:
                raise Blocked("proxy 502")
            r.raise_for_status()

            products = parse_json_products(r.text)
            if not products:
                products = parse_html_products(r.text)

            for p in products:
                p["store_city"]     = None
                p["store_zip"]      = zipcode
                p["search_keyword"] = keyword
            return products

        except (Blocked, requests.RequestException) as e:
            last_err = e
            wait = 1.0 + random.random() * 2.0  # 1–3s
            print(f"  attempt {attempt}/{max_attempts} for ZIP {zipcode}, KW '{keyword}'"
                  f" -> {type(e).__name__}: {e}; rotating… (sleep {wait:.1f}s)")
            time.sleep(wait)

    print(f"  !! gave up (requests) on ZIP {zipcode}, KW '{keyword}': {type(last_err).__name__}: {last_err}")
    return []

# --- Playwright path (browser; bypasses Akamai) --------------------------------
def fetch_with_playwright(zipcode: int, keyword: str, wait_secs: float = 5.0, headless: bool = False):
    """
    Render Walmart search results with Chromium via Bright Data proxy.
    - Uses one global sticky proxy session for the entire run (reduces fingerprint churn)
    - Sets AK timezone + geolocation
    - Waits for real content; slow-scrolls to trigger lazy loading
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception as e:
        raise RuntimeError(
            "Playwright is not installed. Install with:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium\n"
        ) from e

    proxy_user   = f"{BRD_USER_BASE}-session-{GLOBAL_PW_SESSION_ID}"
    proxy_server = f"http://{BRD_HOST}:{BRD_PORT}"
    url          = f"https://www.walmart.com/search?q={requests.utils.quote(keyword)}&postalCode={zipcode}"

    # Anchorage-ish coordinates; use timezone America/Anchorage
    ak_geo = {"longitude": -149.9003, "latitude": 61.2181}
    tz_id  = "America/Anchorage"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--start-maximized",
            ],
        )

        context = browser.new_context(
            locale="en-US",
            timezone_id=tz_id,
            viewport={"width": 1366, "height": 768},
            device_scale_factor=1.0,
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            proxy={"server": proxy_server, "username": proxy_user, "password": BRD_PASS},
            java_script_enabled=True,
            accept_downloads=False,
            geolocation=ak_geo,
            permissions=["geolocation"],
        )

        page = context.new_page()

        # Extra headers help a bit with consistency
        page.set_extra_http_headers({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })

        # Navigate & early wait
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # If we land on a block, try one reload
        if "blocked?" in page.url.lower():
            time.sleep(2.0)
            page.reload(wait_until="domcontentloaded")
            time.sleep(2.0)

        # Let XHRs settle
        try:
            page.wait_for_load_state("networkidle", timeout=30_000)
        except PWTimeout:
            pass

        # Slow-scroll to force tiles to render/lazy-load
        try:
            for _ in range(8):
                page.mouse.wheel(0, 1600)
                time.sleep(0.6)
        except Exception:
            pass

        # Another brief idle wait
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PWTimeout:
            pass

        # If still blocked, bail early
        if "blocked?" in page.url.lower():
            context.close()
            browser.close()
            return []

        # Prefer JSON via __NEXT_DATA__ (fewer DOM fragilities)
        products = []
        try:
            tag = page.locator("script#__NEXT_DATA__").first
            if tag.count() > 0:
                json_text = tag.text_content()
                products = parse_json_products(json_text) if json_text else []
        except Exception:
            products = []

        # Fallback to DOM
        if not products:
            html = page.content()
            products = parse_html_products(html)

        for pitem in products:
            pitem["store_city"]     = None
            pitem["store_zip"]      = zipcode
            pitem["search_keyword"] = keyword

        context.close()
        browser.close()
        return products

# --- Hybrid fetch (requests first, then browser) --------------------------------
def fetch_products(zipcode: int, keyword: str):
    # Try requests twice (cheap). If blocked, use the browser (headful first for visibility)
    rows = fetch_with_requests(zipcode, keyword, max_attempts=2)
    if rows:
        return rows
    print(f"  switching to Playwright for ZIP {zipcode}, KW '{keyword}'…")
    return fetch_with_playwright(zipcode, keyword, wait_secs=5.0, headless=False)

# --- Main ----------------------------------------------------------------------
def main():
    # Load search lists
    df_items, df_zips, KEYWORDS, ZIPS = load_search_lists(SEARCH_LIST_FILE)
    print(df_items.head())
    print(df_zips.head())

    # Proxy/SSL sanity
    proxy_smoke_test()

    # Scrape
    all_rows = []
    for z in ZIPS:
        for kw in KEYWORDS:
            print(f"[ZIP {z}] '{kw}'", flush=True)
            rows = fetch_products(z, kw)
            print(f"  -> {len(rows)} products", flush=True)
            all_rows.extend(rows)
            time.sleep(0.8 + random.random() * 0.7)  # gentle pacing (0.8–1.5s)

    df = pd.DataFrame(all_rows, columns=[
        "store_city", "store_zip",
        "product_name", "product_description",
        "product_price", "product_weight_or_size",
        "upc", "product_id", "search_keyword"
    ])
    print(df.head(10))
    df.to_csv("walmart_results.csv", index=False)
    print("Saved -> walmart_results.csv")

if __name__ == "__main__":
    main()
