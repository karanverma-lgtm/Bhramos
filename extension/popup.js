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
document.addEventListener("DOMContentLoaded", () => {
  fetchLinkedInCookie();

  // Show/hide WhatsApp section based on Enrich toggle
  const enrichCheckbox = document.getElementById("enrich");
  const whatsappSection = document.getElementById("whatsappSection");
  const campaignSection = document.getElementById("campaignSection");
  const whatsappCheckbox = document.getElementById("whatsapp");

  enrichCheckbox.addEventListener("change", () => {
    if (!enrichCheckbox.checked) {
      whatsappCheckbox.checked = false;
      campaignSection.style.display = "none";
    }
  });

  whatsappCheckbox.addEventListener("change", () => {
    campaignSection.style.display = whatsappCheckbox.checked ? "block" : "none";
    // WhatsApp requires enrichment for phone numbers
    if (whatsappCheckbox.checked) {
      enrichCheckbox.checked = true;
    }
  });
});

// Start scraping
document.getElementById("start").addEventListener("click", async () => {
  const statusDiv = document.getElementById("status");
  const configText = document.getElementById("config").value;
  const startBtn = document.getElementById("start");

  try {
    const config = JSON.parse(configText);
    const startPage = parseInt(document.getElementById("startPage").value) || 1;
    const endPage = parseInt(document.getElementById("endPage").value) || startPage;
    const cookie = document.getElementById("cookie").value;
    const filename = document.getElementById("filename").value.trim() || "scraped_data";
    const enrich = document.getElementById("enrich").checked;
    const whatsapp = document.getElementById("whatsapp").checked;
    const campaignName = document.getElementById("campaignName").value.trim() || "default_campaign";

    if (!cookie) {
      throw new Error("li_at cookie is required. Log into LinkedIn first.");
    }

    if (endPage < startPage) {
      throw new Error("End page cannot be less than start page.");
    }

    // Inject pagination info into config
    if (!config.pagination) config.pagination = {};
    config.pagination.start_page = startPage;
    config.pagination.end_page = endPage;

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.url) {
      throw new Error("No active tab found or URL inaccessible.");
    }

    startBtn.disabled = true;
    startBtn.innerHTML = '<span class="icon">⌛</span> Scraping...';
    statusDiv.className = "status loading";
    let statusMsg = "Sending to backend...";
    if (enrich && whatsapp) statusMsg = "Scraping + Enriching + WhatsApp (this may take a few minutes)...";
    else if (enrich) statusMsg = "Scraping + Enriching (this may take a minute)...";
    statusDiv.innerText = statusMsg;

    console.log("Config:", config);
    console.log("URL:", tab.url);
    console.log("Enrich:", enrich);
    console.log("WhatsApp:", whatsapp, "Campaign:", campaignName);

    const response = await fetch("http://127.0.0.1:5000/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: tab.url,
        config: config,
        cookie: cookie,
        filename: filename,
        enrich: enrich,
        whatsapp: whatsapp,
        campaignName: campaignName
      })
    });

    console.log("Response:", response.status);

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Failed to scrape");
    }

    const result = await response.json();
    const scrapedData = result.data;

    // --- Firebase Integration (REST API) ---
    statusDiv.innerText = "📤 Storing data in Firebase...";
    
    const firebaseConfig = {
      apiKey: "AIzaSyCT59RmQGjoVRiSfeytolrETrqtp-4XaIM",
      projectId: "bhramos-ed537"
    };

    try {
      // Store each record in Firestore
      // We use the REST API to avoid CSP issues with external SDKs
      const collectionName = "scraped_profiles";
      
      // Batching or sequential upload
      for (const record of scrapedData) {
        // Convert JS object to Firestore document format
        const fields = {};
        for (const [key, value] of Object.entries(record)) {
          if (value === null || value === undefined) continue;
          fields[key] = { stringValue: String(value) };
        }
        
        // Add dataset and timestamp explicitly at the end
        fields["dataset"] = { stringValue: filename || "default_dataset" };
        fields["created_at"] = { stringValue: new Date().toISOString() };

        // Use sanitized linkedin_url as a unique Document ID
        let docId = "unknown_profile";
        if (record.link) {
          // Remove protocol and trailing slashes, replace / with _
          docId = record.link.replace(/^https?:\/\//, "").replace(/\/$/, "").replace(/[\/\.]/g, "_");
        } else if (record.linkedin_url) {
          docId = record.linkedin_url.replace(/^https?:\/\//, "").replace(/\/$/, "").replace(/[\/\.]/g, "_");
        }

        console.log(`Upserting to Firebase (ID: ${docId}):`, fields);

        const fbResponse = await fetch(`https://firestore.googleapis.com/v1/projects/${firebaseConfig.projectId}/databases/(default)/documents/${collectionName}/${docId}?key=${firebaseConfig.apiKey}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fields })
        });
        
        if (!fbResponse.ok) {
          const fbError = await fbResponse.json();
          console.error(`Firebase API Error for ${docId}:`, fbError);
        }
      }
      console.log("Firebase storage successful");
    } catch (firebaseError) {
      console.error("Firebase Storage Error:", firebaseError);
      // We don't throw here so the user still gets their CSV
    }

    // --- CSV Download ---
    // Convert JSON to CSV for download
    const headers = Object.keys(scrapedData[0]);
    const csvContent = [
      headers.join(","),
      ...scrapedData.map(row => headers.map(h => `"${String(row[h] || "").replace(/"/g, '""')}"`).join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    
    const safeName = filename.replace(/[^a-zA-Z0-9_-]/g, '_');
    await chrome.downloads.download({
      url: url,
      filename: `${safeName}.csv`
    });

    statusDiv.className = "status success";
    statusDiv.innerText = "✅ Done! Data stored in Firebase & CSV downloaded.";
  } catch (error) {
    console.error(error);
    statusDiv.className = "status error";
    statusDiv.innerText = "❌ " + error.message;
  } finally {
    startBtn.disabled = false;
    startBtn.innerHTML = '<span class="icon">🚀</span> Start Scraping';
  }
});
