from scrapling import Fetcher
import pandas as pd

def test_manual():
    # Example: Scraping a public news site or similar
    url = "https://news.ycombinator.com/"
    config = {
        "container": "//tr[@class='athing']",
        "fields": {
            "title": ".//span[@class='titleline']/a/text()",
            "link": ".//span[@class='titleline']/a/@href"
        },
        "pagination": {
            "type": "next",
            "xpath": "//a[@class='morelink']",
            "max_pages": 2
        }
    }

    fetcher = Fetcher()
    results = []
    current_url = url
    pages = 0

    while current_url and pages < config["pagination"]["max_pages"]:
        print(f"Fetching {current_url}...")
        response = fetcher.get(current_url)
        containers = response.xpath(config["container"])
        print(f"Found {len(containers)} items")
        
        for item in containers:
            row = {}
            for key, xp in config["fields"].items():
                row[key] = item.xpath(xp).get()
            results.append(row)
        
        pages += 1
        next_path = config["pagination"]["xpath"]
        next_link = response.xpath(next_path).attrib.get("href")
        if next_link:
            if next_link.startswith("http"):
                current_url = next_link
            else:
                current_url = "https://news.ycombinator.com/" + next_link
        else:
            current_url = None

    df = pd.DataFrame(results)
    print(df.head())
    df.to_csv("test_output.csv", index=False)
    print("Test complete. Results saved to test_output.csv")

if __name__ == "__main__":
    test_manual()
