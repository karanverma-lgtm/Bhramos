import os
import requests
import json
from dotenv import load_dotenv

# Load .env from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

API_KEY = os.getenv("salesql_api")
TEST_URL = "https://www.linkedin.com/in/gauravaroragrv/"

def test_single_enrich():
    print(f"--- SalesQL SINGLE API Test ---")
    print(f"Target URL: {TEST_URL}")
    
    if not API_KEY:
        print("ERROR: API Key not found in .env")
        return

    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "linkedin_url": TEST_URL,
        "match_if_direct_email": "false",
        "match_if_direct_phone": "false"
    }
    
    print("\nSending GET request (Timeout: 120s)...")
    try:
        response = requests.get(
            "https://api-public.salesql.com/v1/persons/enrich",
            headers=headers,
            params=params,
            timeout=120
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n--- FULL JSON RESPONSE ---")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error Response: {response.text}")
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_single_enrich()
