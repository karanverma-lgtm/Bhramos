"""
Test script for AiSensy WhatsApp Campaign API
Sends a test message to a single phone number.
"""
import requests
import json
from dotenv import load_dotenv
import os

# Load .env from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

AISENSY_API_KEY = os.getenv("aisensy_api")

if not AISENSY_API_KEY:
    print("[ERROR] aisensy_api not found in .env file!")
    exit(1)

print(f"AiSensy API Key: [OK] Loaded ({len(AISENSY_API_KEY)} chars)")

# Test payload
payload = {
    "apiKey": AISENSY_API_KEY,
    "campaignName": "TASC1and2",
    "destination": "919015725735",
    "userName": "Erickson Coaching (Nov)",
    "templateParams": [
        "User"
    ],
    "source": "new-landing-page form",
    "media": {
        "url": "https://www.erickson.co.in/wp-content/uploads/2026/01/TASC1and2.jpeg",
        "filename": "TASC1and2"
    },
    "buttons": [],
    "carouselCards": [],
    "location": {},
    "attributes": {},
    "paramsFallbackValue": {
        "FirstName": "user"
    }
}

print(f"\nSending WhatsApp message to: {payload['destination']}")
print(f"Campaign: {payload['campaignName']}")
print(f"Media URL: {payload['media']['url']}")

try:
    resp = requests.post(
        "https://backend.aisensy.com/campaign/t1/api/v2",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30
    )
    
    print(f"\nResponse Status: {resp.status_code}")
    print(f"Response Body: {json.dumps(resp.json(), indent=2)}")
    
    if resp.status_code == 200:
        print("\n✅ WhatsApp message sent successfully!")
    else:
        print(f"\n❌ Failed with status {resp.status_code}")

except Exception as e:
    print(f"\n❌ Error: {str(e)}")
