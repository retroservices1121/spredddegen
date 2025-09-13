import os
import time
import tweepy
import requests
import logging
from datetime import datetime
from supabase import create_client, Client
from typing import List, Dict, Optional

# --- LOGGING SETUP ---
# Railway-optimized logging (stdout only for Railway logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only stdout for Railway
    ]
)
logger = logging.getLogger(__name__)

# --- ENV VARS ---
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN")  # For API v2
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Validate environment variables
required_vars = [
    "TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", 
    "TWITTER_ACCESS_SECRET", "TWITTER_BEARER_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"
]

missing_vars = [var for var in required_vars if not os.environ.get(var)]
if missing_vars:
    logger.error(f"Missing environment variables: {missing_vars}")
    exit(1)

# --- SUPABASE CLIENT ---
try:
    supabase: Client = create_client(
        supabase_url=SUPABASE_URL, 
        supabase_key=SUPABASE_KEY
    )
    logger.info("Supabase client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    exit(1)

# --- TWEEPY CLIENTS ---
# OAuth 1.1 for posting tweets
auth = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY,
    TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET
)
api = tweepy.API(auth, wait_on_rate_limit=True)

# API v2 client for better functionality
client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET,
    wait_on_rate_limit=True
)

# --- TRACK LAST REPLIED MENTION ---
LAST_MENTION_FILE = "last_mention_id.txt"

def get_last_mention_id() -> Optional[int]:
    """Get the ID of the last processed mention"""
    if os.path.exists(LAST_MENTION_FILE):
        try:
            with open(LAST_MENTION_FILE, "r") as f:
                mention_id = int(f.read().strip())
                logger.info(f"Last processed mention ID: {mention_id}")
                return mention_id
        except (ValueError, IOError) as e:
            logger.error(f"Error reading last mention ID: {e}")
    return None

def set_last_mention_id(mention_id: int) -> None:
    """Save the ID of the last processed mention"""
    try:
        with open(LAST_MENTION_FILE, "w") as f:
            f.write(str(mention_id))
        logger.info(f"Updated last mention ID to: {mention_id}")
    except IOError as e:
        logger.error(f"Error saving last mention ID: {e}")

# --- GET LIVE MARKETS FROM SUPABASE ---
def get_live_markets(limit: int = 10) -> List[Dict]:
    """Fetch live markets from Supabase"""
    try:
        # Get current timestamp for comparison
        now = datetime.utcnow().isoformat()
        
        response = supabase.table("markets").select("*")\
            .gt("expiry_date", now)\
            .eq("status", "live")\
            .order("created_at", desc=True)\
            .limit(limit).execute()
        
        markets = response.data
        logger.info(f"Retrieved {len(markets)} live markets")
        return markets
    except Exception as e:
        logger.error(f"Error fetching live markets: {e}")
        return []

# --- FORMAT MARKET TWEET ---
def format_market_tweet(market: Dict, index: int, total: int) -> str:
    """Format a market into a tweet"""
    text = f"🎯 Market {index}/{total}: {market.get('title', market.get('description', 'Unknown Market'))}"
    
    if market.get('question'):
        # Truncate question if too long
        question = market['question']
        if len(question) > 100:
            question = question[:97] + "..."
        text += f"\n❓ {question}"
    
    # Format expiry date
    try:
        expiry = datetime.fromisoformat(market['expiry_date'].replace('Z', '+00:00'))
        expiry_str = expiry.strftime("%b %d, %Y at %H:%M UTC")
        text += f"\n⏰ Expires: {expiry_str}"
    except:
        text += f"\n⏰ Expires: {market.get('expiry_date', 'Unknown')}"
    
    # Add market URL if available
    if market.get('id'):
        text += f"\n🔗 spredd.markets/market/{market['id']}"
    
    # Ensure tweet is under character limit
    if len(text) > 280:
        # Truncate description while keeping important info
        max_desc_len = 280 - len(text) + len(market.get('title', market.get('description', '')))
        if max_desc_len > 20:
            truncated_desc = market.get('title', market.get('description', ''))[:max_desc_len-3] + "..."
            text = f"🎯 Market {index}/{total}: {truncated_desc}"
            if market.get('question'):
                text += f"\n❓ {question}"
            text += f"\n⏰ Expires: {expiry_str}"
            if market.get('id'):
                text += f"\n🔗 spredd.markets/market/{market['id']}"
    
    return text

# --- DOWNLOAD AND UPLOAD IMAGE ---
def upload_market_image(image_url: str) -> Optional[str]:
    """Download and upload market image to Twitter"""
    try:
        response = requests.get(image_url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Save temporarily
        temp_filename = f"temp_image_{int(time.time())}.jpg"
        with open(temp_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Upload to Twitter
        media = api.media_upload(filename=temp_filename)
        
        # Clean up
        os.remove(temp_filename)
        
        logger.info(f"Successfully uploaded image: {media.media_id}")
        return media.media_id
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        return None

# --- REPLY TO MENTIONS ---
def check_mentions() -> None:
    """Check for new mentions and reply with live markets"""
    try:
        last_id = get_last_mention_id()
        
        # Get mentions using API v2 for better functionality
        mentions = client.get_mentions(
            since_id=last_id,
            max_results=10,
            tweet_fields=['created_at', 'author_id', 'conversation_id']
        )
        
        if not mentions.data:
            logger.info("No new mentions found")
            return
        
        # Sort mentions by created_at (oldest first)
        mentions_list = sorted(mentions.data, key=lambda x: x.created_at)
        
        for mention in mentions_list:
            try:
                logger.info(f"Processing mention from user {mention.author_id}")
                
                # Get live markets
                live_markets = get_live_markets(limit=5)  # Limit to 5 for thread readability
                
                if not live_markets:
                    # Reply with no markets message
                    client.create_tweet(
                        text="No live markets available at the moment. Check back soon! 📊",
                        in_reply_to_tweet_id=mention.id
                    )
                    logger.info("Replied with no markets message")
                    continue
                
                # Create thread
                thread_ids = []
                
                # First tweet (thread header)
                first_tweet_text = f"🚀 Here are {len(live_markets)} live Spredd Markets! #SpreddTheWord\n\n🧵 Thread below 👇"
                first_tweet = client.create_tweet(
                    text=first_tweet_text,
                    in_reply_to_tweet_id=mention.id
                )
                thread_ids.append(first_tweet.data['id'])
                logger.info("Created thread header tweet")
                
                # Create a tweet for each market
                for i, market in enumerate(live_markets, 1):
                    try:
                        tweet_text = format_market_tweet(market, i, len(live_markets))
                        
                        # Check if market has an image
                        media_id = None
                        if market.get('image_url'):
                            media_id = upload_market_image(market['image_url'])
                        
                        # Create tweet
                        tweet_params = {
                            'text': tweet_text,
                            'in_reply_to_tweet_id': thread_ids[-1]
                        }
                        
                        if media_id:
                            tweet_params['media_ids'] = [media_id]
                        
                        tweet = client.create_tweet(**tweet_params)
                        thread_ids.append(tweet.data['id'])
                        logger.info(f"Created tweet for market {i}")
                        
                        # Small delay between tweets to avoid rate limiting
                        time.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"Error creating tweet for market {i}: {e}")
                        continue
                
                # Add closing tweet with website link
                closing_tweet = client.create_tweet(
                    text="📈 Explore all markets at spredd.markets\n\n🔔 Follow for live market updates!",
                    in_reply_to_tweet_id=thread_ids[-1]
                )
                
                logger.info(f"Successfully created thread with {len(thread_ids)} tweets")
                
            except Exception as e:
                logger.error(f"Error processing mention {mention.id}: {e}")
                continue
            
            # Save the last processed mention ID
            set_last_mention_id(mention.id)
            
            # Delay between processing mentions
            time.sleep(5)
            
    except Exception as e:
        logger.error(f"Error in check_mentions: {e}")

# --- HEALTH CHECK ---
def health_check() -> bool:
    """Perform basic health checks"""
    try:
        # Test Twitter API
        me = client.get_me()
        if not me.data:
            logger.error("Twitter API health check failed")
            return False
        
        # Test Supabase
        supabase.table("markets").select("id").limit(1).execute()
        
        logger.info("Health check passed")
        return True
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

# --- MAIN POLLING LOOP ---
def main():
    """Main bot execution loop"""
    logger.info("Starting Spredd Markets Twitter Bot")
    
    # Initial health check
    if not health_check():
        logger.error("Initial health check failed. Exiting.")
        exit(1)
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            check_mentions()
            consecutive_errors = 0  # Reset error counter on success
            
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error in main loop (attempt {consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"Too many consecutive errors ({max_consecutive_errors}). Exiting.")
                break
            
            # Exponential backoff on errors
            sleep_time = min(300, 60 * (2 ** consecutive_errors))  # Max 5 minutes
            logger.info(f"Sleeping for {sleep_time} seconds before retry")
            time.sleep(sleep_time)
            continue
        
        # Regular polling interval
        logger.info("Sleeping for 60 seconds")
        time.sleep(60)

if __name__ == "__main__":
    main()
