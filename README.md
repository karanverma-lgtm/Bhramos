# Bhramos Hybrid Scraper

A production-grade hybrid scraping system using a Chrome Extension and a Flask/Scrapling backend.

## 🚀 Setup Instructions

### 1. Backend (Flask + Scrapling)
- Navigate to the `backend` folder.
- Install dependencies: `pip install -r requirements.txt`
- Run the server: `python app.py`
- The server will run on `http://localhost:5000`.

### 2. Chrome Extension
- Open Chrome and go to `chrome://extensions/`.
- Enable **Developer mode** (top right).
- Click **Load unpacked**.
- Select the `extension` folder from this project.

## 🛠️ How to Use
1. Open the website you want to scrape.
2. Click the **Bhramos Scraper** icon in your extension toolbar.
3. Configure your XPaths in the JSON editor:
   - `container`: The XPath for the repeating element (e.g., product card, search result).
   - `fields`: The sub-XPaths for specific data points relative to the container.
   - `pagination`: Configuration for multi-page scraping.
4. Click **Start Scraping**.
5. Wait for the process to complete; a CSV file will be downloaded automatically.

## 🔧 Config Format
```json
{
  "container": "//div[@class='item']",
  "fields": {
    "title": ".//h2/text()",
    "link": ".//a/@href"
  },
  "pagination": {
    "type": "next",
    "xpath": "//a[text()='Next']",
    "max_pages": 5
  }
}
```
