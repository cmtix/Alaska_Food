

import os
import requests
from bs4 import BeautifulSoup
import runpy
import pandas as pd
import requests, os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.request
import ssl


# Execute the file and capture its variables
data = runpy.run_path("WM_search_list_Aug 2025.txt")

# Get lists from the file
items = data["item_list"]
zips = data["zip_codes"]

# Convert to DataFrames
df_items = pd.DataFrame(items, columns=["item"])
df_zips = pd.DataFrame(zips, columns=["zip_code"])

print(df_items.head())
print(df_zips.head())

# CONVERT TO LIST FOR LOOP----

KEYWORDS = df_items["item"].tolist()
ZIPS = df_zips["zip_code"].tolist()

# DEFINE PROXIES----
# Per Bright Data:
API_KEY = 'c87046c5-763d-4077-93c2-f011b5279c7b'

CUSTOMER_ID = "hl_a394e9a7"
ZONE = "residential_proxy1"
ZONE_PASSWORD = "n51uj6o186v8"  # your real zone password

PROXY_HOST = "brd.superproxy.io"
PROXY_PORT = 33335   # check your Bright Data dashboard


#PROXY_USER = f"brd-customer-{CUSTOMER_ID}-zone-{ZONE}-country-us"
#PROXY_USER = "brd-customer-hl_a394e9a7-zone-residential_proxy1"
# You can include targeting (country/state/city/zip) here:
PROXY_USER = f"brd-customer-{CUSTOMER_ID}-zone-{ZONE}-state-ak"
proxy_auth = f"{PROXY_USER}:{ZONE_PASSWORD}"

proxies = {
    "http": f"http://{proxy_auth}@{PROXY_HOST}:{PROXY_PORT}",
    "https": f"http://{proxy_auth}@{PROXY_HOST}:{PROXY_PORT}",
}



# REVISION


CUSTOMER_ID   = "hl_a394e9a7"
ZONE          = "residential_proxy1"
PW            = "n51uj6o186v8"
HOST          = "brd.superproxy.io"

# IMPORTANT: Confirm the exact port in your Bright Data dashboard.
# 22225 is the common default; your earlier attempts used 33335 and failed auth.
PORT          = int(os.environ.get("BD_PORT", "33335"))

# Start with the most permissive targeting (country only). Add state/zip later *if your zone supports it*.
USERNAME      = f"brd-customer-hl_a394e9a7-zone-residential_proxy1"
proxy_url     = f"http://{USERNAME}:{PW}@{HOST}:{PORT}"
proxies       = {"http": proxy_url, "https": proxy_url}

def make_session():
    s = requests.Session()
    s.proxies.update(proxies)
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[429,500,502,503,504], allowed_methods=["GET"])
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

s = make_session()

try:
    # use a simple endpoint
    resp = s.get("https://httpbin.org/ip", timeout=20)
    print("Proxy OK:", resp.status_code, resp.text[:200])
except requests.exceptions.ProxyError as e:
    print("ProxyError:", e)
except Exception as e:
    print("Other error:", type(e).__name__, e)


# Robust session with retries
def make_session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET", "POST"])
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.proxies.update(proxies)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                      " AppleWebKit/537.36 (KHTML, like Gecko)"
                      " Chrome/126.0.0.0 Safari/537.36"
    })
    return s

# 1) Smoke test to validate proxy credentials
s = make_session()
r = s.get("https://httpbin.org/ip", timeout=30)
print("Proxy OK:", r.status_code, r.text[:200])




# LOOP



def make_session(proxies: dict) -> requests.Session:
    """
    Create a robust requests.Session with retries, UA, and proxies.
    """
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.proxies.update(proxies)
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    })
    return s


def proxy_smoke_test(session: requests.Session):
    """
    Validate proxy credentials before scraping Walmart.
    """
    r = session.get("https://httpbin.org/ip", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    print("Proxy OK:", r.status_code, r.text.strip()[:200])


# ---- Walmart helpers (skeletons with TODOs) ---------------------------------
def get_alaska_stores(session: requests.Session):
    """
    NOTE: Walmart store finder pages are JS-rendered; plain HTML may not contain store items.
    Prefer JSON endpoints or Bright Data's headless browser if needed.

    This function is left as a placeholder. If you have a known JSON endpoint,
    replace the logic here. Otherwise, consider switching to ZIP-based search.
    """
    url = "https://www.walmart.com/store/finder?location=Alaska"
    r = session.get(url, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    stores = []
    # TODO: likely empty without JS rendering. If you find a JSON blob, parse it here.
    for store in soup.select(".store-list-item"):
        city = store.select_one(".store-city").text.strip()
        zip_code = store.select_one(".store-zip").text.strip()
        store_id = store.get("data-store-id")
        stores.append({"id": store_id, "city": city, "zip": zip_code})

    return stores


def search_products_by_zip(session: requests.Session, zipcode: int, keyword: str):
    """
    Search Walmart by ZIP + keyword and parse results from the JSON blob if present.
    Returns list of dicts with fields you care about.
    """
    # URL patterns shift; this form typically respects ZIP in query params.
    url = f"https://www.walmart.com/search?q={requests.utils.quote(keyword)}&postalCode={zipcode}"

    r = session.get(url, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()

    products = []

    # Prefer parsing JSON from the __NEXT_DATA__ script tag for stable fields.
    soup = BeautifulSoup(r.text, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if script and script.string:
        try:
            data = json.loads(script.string)
            # The structure can change; guard everything.
            # Example path (subject to change!):
            stacks = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("searchResult", {})
                    .get("itemStacks", [])
            )
            for stack in stacks:
                for item in stack.get("items", []):
                    # Common fields (may vary):
                    title = item.get("title")
                    us_item_id = item.get("usItemId")
                    upc = item.get("upc")
                    price_display = (
                        item.get("price", {}).get("priceDisplay")
                        or item.get("priceInfo", {}).get("currentPrice", {}).get("priceString")
                    )
                    # You can add more fields here (weight/size often lives in variants or specs)
                    products.append({
                        "store_city": None,             # unknown in ZIP search; fill later if you map stores
                        "store_zip": zipcode,
                        "product_name": title,
                        "product_price": price_display,
                        "product_id": us_item_id,
                        "upc": upc,
                    })
        except Exception as e:
            print(f"[WARN] JSON parse error for ZIP {zipcode}, keyword '{keyword}': {e}")

    # Fallback DOM scraping (fragile; classes change often) – optional:
    # for card in soup.select("[data-automation-id='productTile']"):
    #     ...

    return products


# ---- Main --------------------------------------------------------------------
def main():
    # 1) Load search lists
    df_items, df_zips, KEYWORDS, ZIPS = load_search_lists(SEARCH_LIST_FILE)
    print(df_items.head())
    print(df_zips.head())

    # 2) Build proxies & session
    proxies = build_proxies(BD_USERNAME, BD_PW)
    session = make_session(proxies)

    # 3) Proxy smoke test (will raise if credentials/port/targeting are wrong)
    proxy_smoke_test(session)

    # 4) Example scrape loop (ZIP + keyword). Keep items/zips separate.
    all_rows = []
    for z in ZIPS:
        for kw in KEYWORDS:
            rows = search_products_by_zip(session, zipcode=z, keyword=kw)
            all_rows.extend(rows)

    # 5) Save results
    df = pd.DataFrame(all_rows)
    print(df.head(10))
    df.to_csv("walmart_results.csv", index=False)
    print("Saved -> walmart_results.csv")


if __name__ == "__main__":
    main()
