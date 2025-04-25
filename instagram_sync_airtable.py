import requests
import time
from datetime import datetime
import os

# Load secrets from environment variables (set via GitHub Actions)
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
ROCKETAPI_TOKEN = "Token " + os.getenv("ROCKETAPI_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_ID = "appTxTTXPTBFwjelH"
TABLE_NAME = "Accounts"
STATS_TABLE = "Statistics"
MAX_RETRIES = 3

headers_airtable = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

headers_rocket = {
    "Authorization": ROCKETAPI_TOKEN,
    "Content-Type": "application/json"
}

def fetch_follower_count(username):
    url = "https://v1.rocketapi.io/instagram/user/get_info"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(url, headers=headers_rocket, json={"username": username})
            response.raise_for_status()
            data = response.json()
            return data["response"]["body"]["data"]["user"]["edge_followed_by"]["count"]
        except Exception as e:
            print(f"   ⚠️ API error for {username}: {e} (attempt {attempt})")
            time.sleep(2)
    return None

def get_airtable_records():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    response = requests.get(url, headers=headers_airtable)
    response.raise_for_status()
    return response.json()["records"]

def update_airtable_record(record_id, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}/{record_id}"
    response = requests.patch(url, headers=headers_airtable, json={"fields": fields})
    response.raise_for_status()

def add_stat_entry(username, followers, change, source_record_id):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{STATS_TABLE}"
    fields = {
        "Username": username,
        "Date": datetime.utcnow().isoformat(),
        "Followers": followers,
        "Change": change,
        "Source Record": [source_record_id]
    }
    response = requests.post(url, headers=headers_airtable, json={"fields": fields})
    response.raise_for_status()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def main():
    print("🔁 Starting Instagram → Airtable sync with stats...")
    records = get_airtable_records()

    active, ad_issues, suspended = [], [], []

    for record in records:
        fields = record["fields"]
        record_id = record["id"]
        username = fields.get("Username")
        threshold = fields.get("Shadowban Threshold", 15)

        if not username:
            print("⚠️ Skipping empty Username")
            continue

        print(f"→ Checking @{username}...")
        followers = fetch_follower_count(username)

        if followers is None:
            fields_to_update = {
                "Status": "Suspended?",
                "Flagged?": True,
                "Last Checked": datetime.utcnow().isoformat()
            }
            update_airtable_record(record_id, fields_to_update)
            suspended.append(username)
            print(f"   ❌ Marked @{username} as Suspended?")
            continue

        previous = fields.get("Current Followers", followers)
        is_flagged = followers < threshold
        change = followers - previous

        status = "✅ OK"
        if is_flagged:
            status = "Ad Issue?"
            ad_issues.append(username)
        else:
            active.append(username)

        fields_to_update = {
            "Previous Followers": previous,
            "Current Followers": followers,
            "Last Checked": datetime.utcnow().isoformat(),
            "Flagged?": is_flagged,
            "Status": status
        }

        try:
            update_airtable_record(record_id, fields_to_update)
            add_stat_entry(username, followers, change, record_id)
            print(f"   ✅ Updated @{username} → {followers} followers (Δ {change})")
        except Exception as e:
            print(f"   🚨 Airtable error: {e}")

    # Send Telegram update
    msg = "📊 <b>Instagram Sync Report</b>\n\n"
    msg += f"✅ <b>Active:</b> {len(active)} → {', '.join(active)}\n"
    msg += f"⚠️ <b>Ad Issue:</b> {len(ad_issues)} → {', '.join(ad_issues)}\n"
    msg += f"❌ <b>Suspended:</b> {len(suspended)} → {', '.join(suspended)}\n"
    send_telegram_message(msg)

    print("\n✅ Sync complete with statistics.")

if __name__ == "__main__":
    main()
