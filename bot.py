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
    response = supabase.table("markets").select("*")\
        .gt("expiry_date", "now()")\
        .limit(limit).execute()
    return response.data

# --- REPLY TO MENTIONS ---
def check_mentions():
    last_id = get_last_mention_id()
    mentions = api.mentions_timeline(since_id=last_id, tweet_mode="extended")
    mentions.reverse()  # oldest first

    for mention in mentions:
        print(f"Replying to {mention.user.screen_name}...")
        live_markets = get_live_markets()
        if not live_markets:
            api.update_status(
                f"Hey @{mention.user.screen_name}, there are no live markets at the moment.",
                in_reply_to_status_id=mention.id
            )
            continue

        # Create thread
        thread_ids = []
        first_tweet = api.update_status(
            f"Hey @{mention.user.screen_name}, here are the latest live Spredd Markets #SpreddTheWord 🧵👇",
            in_reply_to_status_id=mention.id
        )
        thread_ids.append(first_tweet.id)

    for market in live_markets:
        text = f"📊 {market['description']}"
    if market.get('question'):
        text += f"\n❓ {market['question']}"
    text += f"\n⏰ Expiry: {market['expiry_date']}"

    if market.get('image'):
        media = api.media_upload(filename="temp.jpg", file=requests.get(market['image'], stream=True).raw)
        tweet = api.update_status(
            status=text,
            in_reply_to_status_id=thread_ids[-1],
            media_ids=[media.media_id]
        )
    else:
        tweet = api.update_status(
            status=text,
            in_reply_to_status_id=thread_ids[-1]
        )
    thread_ids.append(tweet.id)

        # Save last mention id
    set_last_mention_id(mention.id)

# --- POLLING LOOP ---
if __name__ == "__main__":
    while True:
        try:
            check_mentions()
        except Exception as e:
            print("Error:", e)
        time.sleep(60)  # check every 60 seconds
