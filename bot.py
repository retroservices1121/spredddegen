import os
import time
import tweepy
from supabase import create_client, Client

# --- ENV VARS ---
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# --- SUPABASE CLIENT ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- TWEEPY CLIENT ---
auth = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY,
    TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET
)
api = tweepy.API(auth, wait_on_rate_limit=True)

# --- TRACK LAST REPLIED MENTION ---
LAST_MENTION_FILE = "last_mention_id.txt"

def get_last_mention_id():
    if os.path.exists(LAST_MENTION_FILE):
        with open(LAST_MENTION_FILE, "r") as f:
            return int(f.read().strip())
    return None

def set_last_mention_id(mention_id):
    with open(LAST_MENTION_FILE, "w") as f:
        f.write(str(mention_id))

# --- GET LIVE MARKETS FROM SUPABASE ---
def get_live_markets(limit=5):
    response = supabase.table("markets").select("*").eq("status", "active").limit(limit).execute()
    return response.data

# ---
