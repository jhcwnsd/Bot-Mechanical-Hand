import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    @classmethod
    def validate(cls):
        missing = []
        if not cls.DISCORD_BOT_TOKEN or cls.DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN":
            missing.append("DISCORD_BOT_TOKEN")
        return missing
