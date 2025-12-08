# WALMART_BRIGHT_DATA2----

# === walmart_ak_scraper.py ====================================================
# ISER – Walmart Emergency Bright Data Scraping (Alaska)
# - Loads item_list and zip_codes from "WM_search_list_Aug 2025.txt"
# - Routes all traffic via Bright Data (username+password, port 33335)
# - Searches Walmart by ZIP + keyword
# - Parses JSON from __NEXT_DATA__ first; falls back to HTML if needed
# - Saves results to walmart_results.csv
# ==============================================================================

# PRE-Setup-----

# See WM_shell_curl.sh

# Libraries
import os
import json
import runpy
import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests


# Bright Data SSL Certificate----

#import certifi, shutil, pathlib

BRIGHTDATA_CA = r"C:/Users/vlcollier/BRIGHT_DATA/brightdata_proxy_ca/brightdata.crt"
COMBINED = str(pathlib.Path(BRIGHTDATA_CA).with_name("combined-ca-bundle.crt"))

# Copy default certifi bundle
shutil.copyfile(certifi.where(), COMBINED)
# Append Bright Data CA
with open(COMBINED, "ab") as out, open(BRIGHTDATA_CA, "rb") as extra:
    out.write(b"\n")
    out.write(extra.read())

# Tell requests to use the combined bundle
os.environ["REQUESTS_CA_BUNDLE"] = COMBINED
os.environ["CURL_CA_BUNDLE"] = COMBINED


# PROXY SET UP----

PROXY = "http://brd-customer-hl_a394e9a7-zone-residential_proxy1:n51uj6o186v8@brd.superproxy.io:33335"
PROXIES = {"http": PROXY, "https": PROXY}


# STATUS TEST ----




BRIGHTDATA_CA = r"C:/Users/vlcollier/BRIGHT_DATA/brightdata_proxy_ca/SSL/brightdata.crt"


print(os.path.exists(BRIGHTDATA_CA))  # should be True

session = requests.Session()
session.proxies.update(PROXIES)
session.verify = BRIGHTDATA_CA

r = requests.get(
    "https://geo.brdtest.com/mygeo.json",
    proxies=PROXIES,
    timeout=30,
    verify=True
)


# ---------------------- Config ------------------------------------------------
SEARCH_LIST_FILE = "WM_search_list_Aug 2025.txt"
DEFAULT_TIMEOUT = 30

# Bright Data proxy — EXACT values from your dashboard (no placeholders)
PROXY = "http://brd-customer-hl_a394e9a7-zone-residential_proxy1:n51uj6o186v8@brd.superproxy.io:33335"
PROXIES = {"http": PROXY, "https": PROXY}

# ---------------------- Load search lists ------------------------------------
def load_search_lists(path: str):
    data = runpy.run_path(path)
    items = data["item_list"]
    zips = data["zip_codes"]

    df_items = pd.DataFrame(items, columns=["item"])
    df_zips = pd.DataFrame(zips, columns=["zip_code"])

    # Separate Python lists for loops
    keywords = df_items["item"].tolist()
    zip_list = df_zips["zip_code"].tolist()
    return df_items, df_zips, keywords, zip_list

# ---------------------- Session / proxy --------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.proxies.update(PROXIES)
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

def proxy_smoke_test(session: requests.Session):
    r = session.get("https://geo.brdtest.com/mygeo.json", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    print("Proxy OK:", r.status_code, r.text.strip()[:200])

# ---------------------- Walmart parsing --------------------------------------
def parse_json_products(html: str):
    """Parse products from Walmart's __NEXT_DATA__ JSON (preferred)."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag or not tag.string:
        return []

    items = []
    try:
        data = json.loads(tag.string)
        stacks = (
            data.get("props", {})
                .get("pageProps", {})
                .get("initialData", {})
                .get("searchResult", {})
                .get("itemStacks", [])
        )
        for stack in stacks:
            for it in stack.get("items", []):
                title = it.get("title")
                us_item_id = it.get("usItemId")
                upc = it.get("upc")

                # price can live in multiple places; try common paths
                price_display = (
                    it.get("price", {}).get("priceDisplay")
                    or it.get("priceInfo", {}).get("currentPrice", {}).get("priceString")
                    or it.get("priceInfo", {}).get("currentPrice", {}).get("price")
                )

                # description/size sometimes embedded in title/attributes; capture what we can
                # (You can extend this if you find richer fields under "attributes"/"secondaryOffer"/"variants")
                desc = it.get("shortDescription") or it.get("description")

                # weight/measurement commonly appears in title or variant attributes;
                # keep a placeholder extraction from title (non-destructive)
                weight_or_size = None
                if title:
                    for tok in ["oz", "fl oz", "lb", "lbs", "pound", "g", "kg", "ct", "pack"]:
                        if tok in title.lower():
                            weight_or_size = tok
                            break

                items.append({
                    "product_name": title,
                    "product_description": desc,
                    "product_price": price_display,
                    "product_weight_or_size": weight_or_size,
                    "upc": upc,
                    "product_id": us_item_id,
                })
    except Exception as e:
        print("[WARN] __NEXT_DATA__ JSON parse error:", e)

    return items

def parse_html_products(html: str):
    """Fallback: parse a few basics from the DOM (fragile)."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    # A safe-ish selector Walmart uses for tiles:
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

def search_products_by_zip(session: requests.Session, zipcode: int, keyword: str):
    url = f"https://www.walmart.com/search?q={requests.utils.quote(keyword)}&postalCode={zipcode}"
    r = session.get(url, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()

    products = parse_json_products(r.text)
    if not products:
        products = parse_html_products(r.text)

    # add zip (city unknown from search page alone)
    for p in products:
        p["store_city"] = None
        p["store_zip"] = zipcode
        p["search_keyword"] = keyword
    return products

# ---------------------- Main --------------------------------------------------
def main():
    df_items, df_zips, KEYWORDS, ZIPS = load_search_lists(SEARCH_LIST_FILE)
    print(df_items.head())
    print(df_zips.head())

    session = make_session()
    proxy_smoke_test(session)  # raises if credentials / port are wrong

    all_rows = []
    for z in ZIPS:
        for kw in KEYWORDS:
            rows = search_products_by_zip(session, zipcode=z, keyword=kw)
            all_rows.extend(rows)

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



# TEST ----
def make_session() -> requests.Session:
    s = requests.Session()
    s.proxies.update(PROXIES)
    s.verify = False   # <— bypass SSL errors (testing only)
    s.headers.update({"User-Agent": "Mozilla/5.0 ..." })
    retries = Retry(total=3, backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET","POST"])
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s
