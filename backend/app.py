from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import pandas as pd
from scrapling import Fetcher
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, urljoin
from dotenv import load_dotenv
import os
import sys
import time
import re
import requests

# Fix Windows console encoding for Unicode characters
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Load .env from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SALESQL_API_KEY = os.getenv("salesql_api")
AISENSY_API_KEY = os.getenv("aisensy_api")

app = Flask(__name__)
CORS(app)

# LinkedIn-specific realistic headers
LINKEDIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# ---------------------------------------------
#  SalesQL Enrichment (New Single Approach)
# ---------------------------------------------
def enrich_profiles(linkedin_urls):
    """
    Send LinkedIn URLs to SalesQL single enrich API one by one.
    """
    if not SALESQL_API_KEY:
        print("[WARN] SALESQL_API_KEY not found in .env")
        return []

    all_enriched = []
    total = len(linkedin_urls)
    
    print(f"\n>>> STARTING ENRICHMENT FOR {total} PROFILES")
    
    for i, url in enumerate(linkedin_urls):
        print(f"[{i+1}/{total}] Enriching: {url.split('/in/')[-1]}...")
        
        # Try up to 2 times for each profile
        for attempt in range(2):
            try:
                params = {
                    "linkedin_url": url,
                    "match_if_direct_email": "false",
                    "match_if_direct_phone": "false"
                }
                
                resp = requests.get(
                    "https://api-public.salesql.com/v1/persons/enrich",
                    headers={"Authorization": f"Bearer {SALESQL_API_KEY}"},
                    params=params,
                    timeout=120 # Increased to 2 minutes
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    # If data has full_name or uuid, it's a valid person object
                    if "full_name" in data or "uuid" in data:
                        all_enriched.append(data)
                        print(f"   [OK] Data found for {data.get('full_name')}")
                        break # Success, move to next profile
                    else:
                        print("   [SKIP] No profile data in response")
                        break
                elif resp.status_code == 429:
                    print(f"   [WAIT] Rate limited (Attempt {attempt+1}). Waiting 10s...")
                    time.sleep(10)
                else:
                    print(f"   [ERR] Status {resp.status_code} on attempt {attempt+1}")
                    if attempt == 1: break # Stop after 2 attempts
                    
            except requests.exceptions.Timeout:
                print(f"   [TIMEOUT] SalesQL took too long (Attempt {attempt+1}). Retrying...")
                if attempt == 1: print("   [SKIP] Giving up after 2 timeouts.")
            except Exception as e:
                print(f"   [ERR] Request failed: {str(e)}")
                break
            
        # Small delay to prevent hitting rate limits
        time.sleep(0.5)
    
    return all_enriched


def clean_phone_number(phone_str):
    """
    Clean phone number: remove +91, spaces, dashes to get a 10-digit number.
    Input examples: '+91 89793 46565', '+91-8979346565', '91 89793 46565'
    Output: '8979346565'
    """
    if not phone_str:
        return ""
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone_str)
    # Remove leading 91 country code if present (results in 10-digit number)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits if len(digits) == 10 else phone_str.strip()


def flatten_person(person):
    """
    Flatten the new SalesQL 'person' schema into a CSV row.
    """
    row = {}
    
    try:
        # Direct fields
        row["full_name"] = person.get("full_name", "")
        row["first_name"] = person.get("first_name", "")
        row["last_name"] = person.get("last_name", "")
        row["linkedin_url"] = person.get("linkedin_url", "")
        row["job_title"] = person.get("title", "")
        row["headline"] = person.get("headline", "")
        
        # Organization
        org = person.get("organization") or {}
        if org:
            row["company_name"] = org.get("name", "")
            row["company_website"] = org.get("website", "")
            row["company_domain"] = org.get("website_domain", "")
        
        # Emails - Extracting valid ones
        emails = person.get("emails", [])
        direct_emails = [e["email"] for e in emails if e.get("type") == "Direct" and e.get("email")]
        work_emails = [e["email"] for e in emails if e.get("type") == "Work" and e.get("email")]
        
        row["direct_email"] = "; ".join(direct_emails)
        row["work_email"] = "; ".join(work_emails)
        
        # Phones — clean to 10-digit format
        phones = person.get("phones", [])
        personal_phones = [clean_phone_number(p["phone"]) for p in phones if p.get("type") == "Personal" and p.get("phone")]
        work_phones = [clean_phone_number(p["phone"]) for p in phones if p.get("type") == "Work" and p.get("phone")]
        
        # Filter out any that didn't clean to 10 digits
        personal_phones = [p for p in personal_phones if len(p) == 10 and p.isdigit()]
        work_phones = [p for p in work_phones if len(p) == 10 and p.isdigit()]
        
        row["personal_phone"] = "; ".join(personal_phones)
        row["work_phone"] = "; ".join(work_phones)
    except Exception as e:
        print(f"  [ERR] Failed to flatten profile {person.get('full_name', 'unknown')}: {str(e)}")
    
    return row


# ---------------------------------------------
#  WhatsApp Campaign via AiSensy
# ---------------------------------------------
def send_whatsapp_campaign(rows, campaign_name):
    """
    Send WhatsApp campaign to all profiles with a personal_phone.
    Uses AiSensy API.
    """
    if not AISENSY_API_KEY:
        print("[WARN] AISENSY_API_KEY not found in .env, skipping WhatsApp campaign")
        return {"sent": 0, "failed": 0, "skipped": 0, "error": "API key missing"}

    sent = 0
    failed = 0
    skipped = 0
    total = len(rows)

    print(f"\n>>> STARTING WHATSAPP CAMPAIGN '{campaign_name}' FOR {total} PROFILES")

    for i, row in enumerate(rows):
        personal_phone = row.get("personal_phone", "")
        first_name = row.get("first_name", "User")
        full_name = row.get("full_name", "User")

        # Only send to valid personal phone numbers
        if not personal_phone or ";" in personal_phone:
            # Take first phone if multiple
            if ";" in personal_phone:
                personal_phone = personal_phone.split(";")[0].strip()
            else:
                print(f"  [{i+1}/{total}] {full_name} — no personal phone, skipping")
                skipped += 1
                continue

        if not (len(personal_phone) == 10 and personal_phone.isdigit()):
            print(f"  [{i+1}/{total}] {full_name} — invalid phone '{personal_phone}', skipping")
            skipped += 1
            continue

        # Add 91 prefix for India
        destination = f"91{personal_phone}"

        payload = {
            "apiKey": AISENSY_API_KEY,
            "campaignName": campaign_name,
            "destination": destination,
            "userName": "Erickson Coaching (Nov)",
            "templateParams": [first_name or "there"],
            "source": "bhramos-scraper",
            "media": {
                "url": "https://www.xmonks.com/TASCMAY.jpg",
                "filename": "TASCMAY"
            },
            "buttons": [],
            "carouselCards": [],
            "location": {},
            "attributes": {},
            "paramsFallbackValue": {
                "FirstName": "there"
            }
        }

        try:
            resp = requests.post(
                "https://backend.aisensy.com/campaign/t1/api/v2",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") == "true":
                    print(f"  [{i+1}/{total}] {full_name} ({destination}) — sent")
                    sent += 1
                else:
                    print(f"  [{i+1}/{total}] {full_name} ({destination}) — API error: {data}")
                    failed += 1
            else:
                err_body = resp.text[:300]
                print(f"  [{i+1}/{total}] {full_name} ({destination}) — HTTP {resp.status_code}: {err_body}")
                failed += 1
        except Exception as e:
            print(f"  [{i+1}/{total}] {full_name} ({destination}) — error: {str(e)}")
            failed += 1

        # Small delay between messages
        time.sleep(0.3)

    print(f"\n>>> CAMPAIGN COMPLETE: {sent} sent, {failed} failed, {skipped} skipped")
    return {"sent": sent, "failed": failed, "skipped": skipped}


# ---------------------------------------------
#  Scrape Endpoint
# ---------------------------------------------
@app.route("/scrape", methods=["POST"])
def scrape():
    try:
        data = request.json
        url = data.get("url")
        config = data.get("config")
        li_at_cookie = data.get("cookie")
        filename = data.get("filename", "scraped_data")
        enrich = data.get("enrich", False)
        whatsapp = data.get("whatsapp", False)
        campaign_name = data.get("campaignName", "default_campaign")
        
        filename = re.sub(r'[^\w\-]', '_', filename)
        
        if not url or not config:
            return jsonify({"error": "Missing URL or config"}), 400

        if not li_at_cookie:
            return jsonify({"error": "LinkedIn requires li_at cookie."}), 400

        headers = dict(LINKEDIN_HEADERS)
        headers["Cookie"] = f"li_at={li_at_cookie}"

        fetcher = Fetcher()
        results = []
        max_pages = int(config.get("pagination", {}).get("max_pages", 1))

        # Clean URL
        u = urlparse(url)
        q = parse_qs(u.query)
        if 'page' in q: del q['page']
        clean_base = urlunparse(u._replace(query=urlencode(q, doseq=True)))

        for p in range(max_pages):
            try:
                curr_url = clean_base
                if p > 0:
                    u = urlparse(clean_base)
                    q = parse_qs(u.query)
                    q['page'] = [str(p + 1)]
                    curr_url = urlunparse(u._replace(query=urlencode(q, doseq=True)))

                print(f"\n--- Page {p+1}/{max_pages} ---")
                resp = fetcher.get(curr_url, headers=headers)
                
                # Use scrapling's own parsed DOM (not raw HTML re-parse)
                profile_links = resp.xpath("//a[contains(@href, '/in/')]")
                print(f"  Found {len(profile_links)} total <a> tags with /in/ links")
                page_results = 0
                skipped = 0
                seen = set()

                for link in profile_links:
                    try:
                        href = link.attrib.get("href", "")
                        if not href:
                            continue

                        m = re.search(r'(/in/[^/?]+)', href)
                        if not m:
                            continue

                        path = m.group(1)
                        if path in seen:
                            continue

                        profile_name = path.replace("/in/", "")

                        # Check if this link is inside a "mutual connection" indicator.
                        skip_profile = False
                        parent = link.parent
                        if parent is not None:
                            parent_text = parent.get_all_text().lower()
                            if "mutual connection" in parent_text:
                                print(f"  [SKIP] {profile_name} — mutual connection indicator")
                                skipped += 1
                                skip_profile = True

                        if skip_profile:
                            continue

                        seen.add(path)
                        results.append({"link": f"https://www.linkedin.com{path}"})
                        page_results += 1
                    except Exception as e:
                        print(f"  [ERR] Failed to process a link: {str(e)}")
                        continue

                print(f"Extracted {page_results} profiles, skipped {skipped} mutual connections.")
            except Exception as e:
                print(f"  [ERR] Failed to scrape page {p+1}: {str(e)}")
            
            if p < max_pages - 1: time.sleep(1.5)

        if not results:
            return jsonify({"error": "No profiles found."}), 404

        # Enrichment
        rows = []
        if enrich:
            try:
                urls = [r["link"] for r in results]
                persons = enrich_profiles(urls)
                rows = [flatten_person(p) for p in persons]
                df = pd.DataFrame(rows)
            except Exception as e:
                print(f"[ERR] Enrichment failed: {str(e)}")
                df = pd.DataFrame(results)
        else:
            df = pd.DataFrame(results)

        df.insert(0, "sr_no", range(1, len(df) + 1))
        df["scraped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # WhatsApp Campaign (only after enrichment, needs personal_phone)
        if whatsapp and enrich and rows:
            try:
                send_whatsapp_campaign(rows, campaign_name)
            except Exception as e:
                print(f"[ERR] WhatsApp campaign failed: {str(e)}")
        elif whatsapp and not enrich:
            print("[WARN] WhatsApp campaign requires enrichment to be enabled (need phone numbers)")
        
        path = os.path.join(os.getcwd(), f"{filename}.csv")
        df.to_csv(path, index=False)
        return send_file(path, as_attachment=True, download_name=f"{filename}.csv")

    except Exception as e:
        print(f"[FATAL] Unhandled error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print(f"SalesQL API Key: {'[OK] Loaded' if SALESQL_API_KEY else '[!!] Missing'}")
    print(f"AiSensy API Key: {'[OK] Loaded' if AISENSY_API_KEY else '[!!] Missing'}")
    app.run(debug=True, host="127.0.0.1", port=5000)
