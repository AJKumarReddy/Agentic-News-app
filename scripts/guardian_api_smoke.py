import os
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GUARDIAN_API_KEY")

url = "https://content.guardianapis.com/search"

params = {
    "api-key": API_KEY,
    "from-date": date.today().isoformat(),
    "order-by": "newest",
    "page-size": 50,
    "page": 1,
    "show-fields": "headline,body,trailText",
    "show-tags": "contributor,keyword"
}

print("API key loaded:", API_KEY is not None)
response = requests.get(url, params=params, timeout=30)
response.raise_for_status()

data = response.json()

articles = data["response"]["results"]

for article in articles[:5]:
    print(article["webTitle"])
    print(article["webPublicationDate"])
    print(article["sectionName"])
    print(article["webUrl"])
    print("-" * 80)