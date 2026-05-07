// Auto-fetch li_at cookie on popup load
async function fetchLinkedInCookie() {
  const statusDiv = document.getElementById("status");
  const cookieInput = document.getElementById("cookie");

  // Check if chrome.cookies API is available
  if (!chrome.cookies) {
    console.error("chrome.cookies API not available. Did you reload the extension?");
    statusDiv.className = "status error";
    statusDiv.innerText = "⚠️ Reload extension in chrome://extensions first!";
    return;
  }

  try {
    // Try multiple URL patterns (LinkedIn sets cookies on different domains)
    const urls = [
      "https://www.linkedin.com",
      "https://linkedin.com",
      "https://www.linkedin.com/"
    ];

    let foundCookie = null;

    // Method 1: Try chrome.cookies.get with each URL
    for (const url of urls) {
      try {
        const cookie = await chrome.cookies.get({ url, name: "li_at" });
        if (cookie && cookie.value) {
          foundCookie = cookie;
          break;
        }
      } catch (e) {
        console.log(`get() failed for ${url}:`, e.message);
      }
    }

    // Method 2: Fallback to getAll if get() didn't work
    if (!foundCookie) {
      try {
        const allCookies = await chrome.cookies.getAll({ domain: ".linkedin.com", name: "li_at" });
        if (allCookies && allCookies.length > 0) {
          foundCookie = allCookies[0];
        }
      } catch (e) {
        console.log("getAll() fallback failed:", e.message);
      }
    }

    if (foundCookie && foundCookie.value) {
      cookieInput.value = foundCookie.value;
      statusDiv.className = "status success";
      statusDiv.innerText = "🔑 li_at cookie auto-detected!";
      console.log("li_at found on domain:", foundCookie.domain);
    } else {
      statusDiv.className = "status error";
      statusDiv.innerText = "⚠️ No li_at found. Log into LinkedIn first.";
    }
  } catch (e) {
    console.error("Cookie fetch error:", e);
    statusDiv.className = "status error";
    statusDiv.innerText = "⚠️ Error: " + e.message;
  }
}

// Run on popup open
document.addEventListener("DOMContentLoaded", fetchLinkedInCookie);

// Start scraping
document.getElementById("start").addEventListener("click", async () => {
  const statusDiv = document.getElementById("status");
  const configText = document.getElementById("config").value;
  const startBtn = document.getElementById("start");

  try {
    const config = JSON.parse(configText);
    const maxPages = document.getElementById("maxPages").value;
    const cookie = document.getElementById("cookie").value;
    const filename = document.getElementById("filename").value.trim() || "scraped_data";
    const enrich = document.getElementById("enrich").checked;

    if (!cookie) {
      throw new Error("li_at cookie is required. Log into LinkedIn first.");
    }

    // Inject max_pages into config
    if (!config.pagination) config.pagination = {};
    config.pagination.max_pages = parseInt(maxPages);

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.url) {
      throw new Error("No active tab found or URL inaccessible.");
    }

    startBtn.disabled = true;
    startBtn.innerHTML = '<span class="icon">⌛</span> Scraping...';
    statusDiv.className = "status loading";
    statusDiv.innerText = enrich ? "Scraping + Enriching (this may take a minute)..." : "Sending to backend...";

    console.log("Config:", config);
    console.log("URL:", tab.url);
    console.log("Enrich:", enrich);

    const response = await fetch("http://127.0.0.1:5000/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: tab.url,
        config: config,
        cookie: cookie,
        filename: filename,
        enrich: enrich
      })
    });

    console.log("Response:", response.status);

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Failed to scrape");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    
    // Sanitize filename and download
    const safeName = filename.replace(/[^a-zA-Z0-9_-]/g, '_');
    await chrome.downloads.download({
      url: url,
      filename: `${safeName}.csv`
    });

    statusDiv.className = "status success";
    statusDiv.innerText = "✅ Done! CSV downloaded.";
  } catch (error) {
    console.error(error);
    statusDiv.className = "status error";
    statusDiv.innerText = "❌ " + error.message;
  } finally {
    startBtn.disabled = false;
    startBtn.innerHTML = '<span class="icon">🚀</span> Start Scraping';
  }
});
