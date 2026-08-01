import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    REDIS_URL = os.getenv("REDIS_URL")

    @classmethod
    def validate(cls):
        missing = []
        if not cls.DISCORD_BOT_TOKEN or cls.DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN":
            missing.append("DISCORD_BOT_TOKEN")
        if not cls.GEMINI_API_KEY or cls.GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
            missing.append("GEMINI_API_KEY")
        return missing
