import os
import time
import pandas as pd
from datetime import datetime
import requests

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --------------------------------------------------------------------
# 1. RETRIEVE TOKEN VIA SELENIUM (ENTER ZIP CODE)
# --------------------------------------------------------------------
def retrieve_token(driver, zip_code):
    """
    Navigate to shopalaskacommercial.com, enter the ZIP code, and retrieve the JWT token from localStorage.
    The session remains open during this process.
    """
    try:
        driver.get("https://shopalaskacommercial.com/")
        time.sleep(5)  # Allow page to load

        wait = WebDriverWait(driver, 10)
        # Locate the ZIP code input field
        zip_input_xpath = "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[2]/input"
        zip_input = wait.until(EC.presence_of_element_located((By.XPATH, zip_input_xpath)))
        zip_input.clear()
        zip_input.send_keys(zip_code)

        # Use a special XPath if needed; otherwise, default
        special_xpaths = {
            '99574': "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[3]/div/button/span"
        }
        select_xpath = special_xpaths.get(zip_code, "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[3]/div/button/span")
        select_button = wait.until(EC.element_to_be_clickable((By.XPATH, select_xpath)))
        select_button.click()

        # Click the Save button to confirm location
        save_button_xpath = "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/button"
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, save_button_xpath)))
        save_button.click()

        time.sleep(10)  # Wait for token to be stored in localStorage
        token = driver.execute_script("return window.localStorage.getItem('token');")
        if token:
            token = token.replace('"', '')
            print("Token retrieved:", token)
            return token
        else:
            print("Token not found in localStorage.")
            return None
    except Exception as e:
        print("Error retrieving token:", e)
        return None

# --------------------------------------------------------------------
# 2. CALL THE API FOR EACH KEYWORD USING "SEARCH_STRING" PARAMETER
# --------------------------------------------------------------------
def search_keyword_payload(token, keyword, store="203"):
    """
    Calls the /storeItem/algolia endpoint with a POST request.
    Uses query parameters (including SEARCH_STRING) to pass the search term.
    """
    url = "https://backend.shopalaskacommercial.com/storeItem/algolia"
    params = {
        "STORE": store,
        "DEPT_ID": "",
        "CLASS_ID": "",
        "PAGE": "1",
        "LIMIT": "50",  # Changed from "30" to "50"
        "SORT": "",
        "ORDER": "",
        "TRENDING_SEARCH": "false",
        "SKU": "",
        "PARTY_TRAY_FLAG": "false",
        "SEARCH_STRING": keyword  # Using the parameter from DevTools
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0"
    }
    # For this endpoint, no additional payload body is needed.
    payload = {}

    # Debug: Print the full request URL
    req = requests.Request("POST", url, params=params, headers=headers, json=payload)
    prepped = req.prepare()
    print("Request URL:", prepped.url)

    response = requests.post(url, params=params, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error for keyword '{keyword}': {response.status_code} {response.text}")
        return None

# --------------------------------------------------------------------
# 3. COLLAPSE THE "response" COLUMN
# --------------------------------------------------------------------
def collapse_response_column(df):
    """
    Explodes the 'response' column (which contains lists of dictionaries) so that each dictionary becomes its own row.
    Top-level fields (like searched_keyword, zip_code, etc.) are retained.
    """
    if "response" not in df.columns:
        print("No 'response' column found to collapse.")
        return df

    df_exploded = df.explode("response").reset_index(drop=True)
    df_exploded = pd.concat(
        [df_exploded.drop(columns=["response"]),
         df_exploded["response"].apply(pd.Series)],
        axis=1
    )
    return df_exploded

# --------------------------------------------------------------------
# 4. SAVE RESULTS TO CSV UNDER "ACC_YY_MM" FOLDER WITH FILENAME "ACC_<STORE>_MM_YY.csv"
# --------------------------------------------------------------------
def save_payload_results(df, store):
    """
    Saves the DataFrame to a CSV file under the folder structure:
    [Base Path]\ACC\ACC_YY_MM\ACC_<STORE>_MM_YY.csv
    """
    now = datetime.now()
    year_last2 = now.strftime("%y")  # e.g., "25"
    month_str = now.strftime("%m")     # e.g., "03"

    base_path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC"
    folder_name = f"ACC_{year_last2}_{month_str}"
    folder_path = os.path.join(base_path, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    file_name = f"ACC_{store}_{month_str}_{year_last2}.csv"
    file_path = os.path.join(folder_path, file_name)

    df.to_csv(file_path, index=False)
    print(f"Payload results saved to {file_path}")

# --------------------------------------------------------------------
# 5. MAIN EXECUTION FLOW
# --------------------------------------------------------------------
def main():
    zip_code = "99574"  # Set your ZIP code here.
    store_id = "203"    # Set your store ID here.

    # 5.1 Start Selenium and retrieve token.
    options = Options()
    # Uncomment the next line to run headless if desired:
    # options.add_argument("--headless")
    driver_service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=driver_service, options=options)

    token = retrieve_token(driver, zip_code)
    if not token:
        driver.quit()
        return
    # Close the Selenium session once the token is retrieved.
    driver.quit()

    # 5.2 Load keywords from CSV (expects a column named "ACC_Keywords")
    keywords_csv_path = r"G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC\ACC_Keywords.csv"
    try:
        keywords_df = pd.read_csv(keywords_csv_path)
        keywords = keywords_df["ACC_Keywords"].tolist()
    except Exception as e:
        print("Error loading keywords from CSV:", e)
        return

    all_payload_results = []
    # 5.3 For each keyword, call the API to retrieve the payload.
    for keyword in keywords:
        print(f"Searching for keyword: {keyword}")
        data = search_keyword_payload(token, keyword, store=store_id)
        if data:
            # Add metadata to the payload
            data["searched_keyword"] = keyword
            data["zip_code"] = zip_code
            all_payload_results.append(data)
        else:
            print(f"No data returned for keyword: {keyword}")

    if not all_payload_results:
        print("No payload data collected.")
        return

    # 5.4 Convert the list of payload dictionaries into a DataFrame.
    df_raw = pd.DataFrame(all_payload_results)
    # 5.5 Collapse (flatten) the "response" column.
    df_flat = collapse_response_column(df_raw)
    # 5.6 Save the final DataFrame.
    save_payload_results(df_flat, store_id)

if __name__ == "__main__":
    main()

