from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import pandas as pd
from scrapling import Fetcher
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, urljoin
from dotenv import load_dotenv
import os
import time
import re
import requests

# Load .env from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SALESQL_API_KEY = os.getenv("salesql_api")

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


def flatten_person(person):
    """
    Flatten the new SalesQL 'person' schema into a CSV row.
    """
    row = {}
    
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
    
    # Phones
    phones = person.get("phones", [])
    personal_phones = [p["phone"] for p in phones if p.get("type") == "Personal" and p.get("phone")]
    work_phones = [p["phone"] for p in phones if p.get("type") == "Work" and p.get("phone")]
    
    row["personal_phone"] = "; ".join(personal_phones)
    row["work_phone"] = "; ".join(work_phones)
    
    return row


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
            curr_url = clean_base
            if p > 0:
                u = urlparse(clean_base)
                q = parse_qs(u.query)
                q['page'] = [str(p + 1)]
                curr_url = urlunparse(u._replace(query=urlencode(q, doseq=True)))

            print(f"\n--- Page {p+1}/{max_pages} ---")
            resp = fetcher.get(curr_url, headers=headers)
            
            links = resp.xpath("//a[contains(@href, '/in/')]/@href")
            page_results = 0
            seen = set()
            
            for l in links:
                href = str(l)
                m = re.search(r'(/in/[^/?]+)', href)
                if m:
                    path = m.group(1)
                    if path not in seen:
                        seen.add(path)
                        results.append({"link": f"https://www.linkedin.com{path}"})
                        page_results += 1
            
            print(f"Extracted {page_results} profiles.")
            if p < max_pages - 1: time.sleep(1.5)

        if not results:
            return jsonify({"error": "No profiles found."}), 404

        # Enrichment
        if enrich:
            urls = [r["link"] for r in results]
            persons = enrich_profiles(urls)
            rows = [flatten_person(p) for p in persons]
            df = pd.DataFrame(rows)
        else:
            df = pd.DataFrame(results)

        df.insert(0, "sr_no", range(1, len(df) + 1))
        df["scraped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        path = os.path.join(os.getcwd(), f"{filename}.csv")
        df.to_csv(path, index=False)
        return send_file(path, as_attachment=True, download_name=f"{filename}.csv")

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print(f"SalesQL API Key: {'[OK] Loaded' if SALESQL_API_KEY else '[!!] Missing'}")
    app.run(debug=True, host="127.0.0.1", port=5000)
