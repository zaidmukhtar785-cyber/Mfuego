import os
from dotenv import load_dotenv

load_dotenv()

def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./fuegos.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url

DATABASE_URL = get_database_url()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://127.0.0.1:8000/auth/callback")
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
SESSION_SECRET = os.getenv("SESSION_SECRET", "CHANGE_THIS_BEFORE_DEPLOYING")
DEFAULT_PREFIX = os.getenv("DEFAULT_PREFIX", "!")

LAVALINK_HOST = os.getenv("LAVALINK_HOST", "")
LAVALINK_PORT = os.getenv("LAVALINK_PORT", "2333")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "")
