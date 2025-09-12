import os
import requests
from supabase import create_client
import tweepy
from dotenv import load_dotenv

load_dotenv()

# --- Supabase Setup ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def get_live_markets(limit=5):
    response = supabase.table("markets")\
        .select("id,title,image_url,expiration_date")\
        .eq("status", "active")\
        .order("expiration_date", desc=False)\
        .limit(limit)\
        .execute()
    return response.data

# --- Twitter Setup ---
client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_API_KEY"),
    consumer_secret=os.getenv("TWITTER_API_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_SECRET"),
    bearer_token=os.getenv("TWITTER_BEARER_TOKEN")
)

def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        file_path = "/tmp/temp.jpg"
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_path
    return None

def post_markets_thread(mention_id, user_handle):
    markets = get_live_markets()
    if not markets:
        client.create_tweet(
            in_reply_to_tweet_id=mention_id,
            text=f"Hey @{user_handle}, there are no live markets at the moment. Check back later!"
        )
        return

    first_tweet = client.create_tweet(
        in_reply_to_tweet_id=mention_id,
        text=f"Hey @{user_handle}, here are the latest live Spredd Markets #SpreddTheWord 🧵👇"
    )
    last_tweet_id = first_tweet.data["id"]

    for m in markets:
        media_id = None
        if m.get("image_url"):
            img_path = download_image(m["image_url"])
            if img_path:
                media = client.media_upload(img_path)
                media_id = media.media_id

        text = f"📊 {m['question']}\n⏰ Expires: {m['expiry_date']}\n🔗 Play: https://spredd.markets/{m['id']}"

        tweet = client.create_tweet(
            in_reply_to_tweet_id=last_tweet_id,
            text=text,
            media_ids=[media_id] if media_id else None
        )
        last_tweet_id = tweet.data["id"]

# --- Streaming Setup ---
class MentionListener(tweepy.StreamingClient):
    def on_tweet(self, tweet):
        if tweet.author_id == client.get_me().data.id:
            return
        if "SpreddDegen" in tweet.text:
            user_data = client.get_user(id=tweet.author_id)
            user_handle = user_data.data.username
            post_markets_thread(tweet.id, user_handle)

if __name__ == "__main__":
    stream = MentionListener(os.getenv("TWITTER_BEARER_TOKEN"))
    stream.add_rules(tweepy.StreamRule("@SpreddDegen"))
    stream.filter(expansions=["author_id"])
