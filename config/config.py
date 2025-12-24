import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_URL = os.getenv("POLYMARKET_API_URL", "https://gamma-api.polymarket.com")
    DB_NAME = "polymarket_bot.db"
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

config = Config()