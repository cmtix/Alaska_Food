# Walmart_Bright_Data3.py
# NOTES:

# RUN RETICULATE3.R FIRST.


# --- Imports -------------------------------------------------------------------
import os
import json
import pathlib
import shutil
import certifi
import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import runpy

# --- Paths / SSL (Bright Data CA + certifi combined bundle) --------------------
BRIGHTDATA_CA = r"C:/Users/vlcollier/BRIGHT_DATA/brightdata_proxy_ca/SSL/brightdata.crt"
assert os.path.exists(BRIGHTDATA_CA), "Bright Data CA file not found"

COMBINED = str(pathlib.Path(BRIGHTDATA_CA).with_name("combined-ca-bundle.crt"))
# build (or rebuild) the combined bundle every run (cheap + deterministic)
shutil.copyfile(certifi.where(), COMBINED)
with open(COMBINED, "ab") as out, open(BRIGHTDATA_CA, "rb") as extra:
    out.write(b"\n")
    out.write(extra.read())

# Make Requests (and curl) trust the combined bundle
os.environ["REQUESTS_CA_BUNDLE"] = COMBINED
os.environ["CURL_CA_BUNDLE"] = COMBINED

# --- Proxy (Alaska targeting) --------------------------------------------------
# If you want stickiness, add: -session-ak1
# AFTER  (country + state)
PROXY = (
    "http://"
    "brd-customer-hl_a394e9a7-zone-residential_proxy1-country-us-state-ak"
    ":n51uj6o186v8@brd.superproxy.io:33335"
)

PROXIES = {"http": PROXY, "https": PROXY}

# --- Config --------------------------------------------------------------------
SEARCH_LIST_FILE = "WM_search_list_Aug 2025.txt"
DEFAULT_TIMEOUT = 30

# --- Session factory ------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.proxies.update(PROXIES)
    # Explicitly trust the combined bundle (in addition to env var)
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
        allowed_methods=["GET", "POST"]
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

# STICKY PROXY per ATTEMPT ----

import random, string, time

BRD_USER_BASE = "brd-customer-hl_a394e9a7-zone-residential_proxy1-country-us-state-ak"
BRD_PASS     = "n51uj6o186v8"
BRD_HOSTPORT = "brd.superproxy.io:33335"

def rand_session(n=8):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

def build_proxies(session_id: str):
    user = f"{BRD_USER_BASE}-session-{session_id}"
    proxy = f"http://{user}:{BRD_PASS}@{BRD_HOSTPORT}"
    return {"http": proxy, "https": proxy}

def make_session_with_proxies(proxies: dict) -> requests.Session:
    s = requests.Session()
    s.proxies.update(proxies)
    s.verify = os.environ.get("REQUESTS_CA_BUNDLE", None) or COMBINED
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.walmart.com/",
    })
    # Let *us* handle 502s instead of Retry spinning on them
    retries = Retry(total=0)
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

# --- Utilities -----------------------------------------------------------------
def proxy_smoke_test(session: requests.Session):
    r = session.get("https://geo.brdtest.com/mygeo.json", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    print("Proxy OK:", r.status_code, r.text.strip()[:200])

def load_search_lists(path: str):
    data = runpy.run_path(path)
    items = data["item_list"]
    zips = data["zip_codes"]

    df_items = pd.DataFrame(items, columns=["item"])
    df_zips = pd.DataFrame(zips, columns=["zip_code"])

    keywords = df_items["item"].tolist()
    zip_list = df_zips["zip_code"].tolist()
    return df_items, df_zips, keywords, zip_list

# --- Walmart parsers ------------------------------------------------------------
def parse_json_products(html: str):
    """Robustly parse products from Walmart's __NEXT_DATA__ JSON."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag or not tag.string:
        return []

    try:
        data = json.loads(tag.string)
    except Exception as e:
        print("[WARN] __NEXT_DATA__ load failed:", e)
        return []

    def g(obj, *keys, default=None):
        cur = obj
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return default if cur is None else cur

    items_out = []

    # prefer pageProps.initialData.* paths, but be defensive
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
        # stack can be dict or list
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
                continue  # avoid 'float' / str etc.

            title = it.get("title")
            us_item_id = it.get("usItemId") or it.get("usItemID")
            upc = it.get("upc")

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
        name_el = card.select_one("a span")
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

class Blocked(Exception):
    pass

def search_products_by_zip(zipcode: int, keyword: str, max_attempts: int = 5):
    """
    Fetch search page with sticky session rotation to dodge blocks.
    """
    url = "https://www.walmart.com/search"
    params = {"q": keyword, "postalCode": zipcode}

    last_err = None
    for attempt in range(1, max_attempts + 1):
        sid = rand_session()
        session = make_session_with_proxies(build_proxies(sid))

        try:
            r = session.get(url, params=params, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
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
                p["store_city"] = None
                p["store_zip"] = zipcode
                p["search_keyword"] = keyword
            return products

        except (Blocked, requests.RequestException) as e:
            last_err = e
            wait = 1.0 + random.random() * 2.0  # 1–3s
            print(f"  attempt {attempt}/{max_attempts} for ZIP {zipcode}, KW '{keyword}' -> {type(e).__name__}: {e}; rotating… (sleep {wait:.1f}s)")
            time.sleep(wait)

    # after attempts exhausted
    print(f"  !! gave up on ZIP {zipcode}, KW '{keyword}': {type(last_err).__name__}: {last_err}")
    return []


# --- Main ----------------------------------------------------------------------
def main():
    df_items, df_zips, KEYWORDS, ZIPS = load_search_lists(SEARCH_LIST_FILE)
    print(df_items.head())
    print(df_zips.head())

    # Proxy/SSL sanity check only
    session = make_session()
    proxy_smoke_test(session)

    all_rows = []
    for z in ZIPS:
        for kw in KEYWORDS:
            print(f"[ZIP {z}] '{kw}'", flush=True)
            rows = search_products_by_zip(z, kw)  # <-- no session arg
            print(f"  -> {len(rows)} products", flush=True)
            all_rows.extend(rows)
            time.sleep(0.8 + random.random()*0.7)  # gentle pacing (0.8–1.5s)

    df = pd.DataFrame(all_rows, columns=[
        "store_city", "store_zip",
        "product_name", "product_description",
        "product_price", "product_weight_or_size",
        "upc", "product_id", "search_keyword"
    ])
    print(df.head(10))
    df.to_csv("walmart_results.csv", index=False)
    print("Saved -> walmart_results.csv")
