import os
import sys
import discord
from config import Config
import discord_actions
from gemini_agent import GeminiAgent

# Reconfigure stdout/stderr to support unicode characters in Windows console
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Validate credentials before starting
missing_envs = Config.validate()
if missing_envs:
    print("Error: Missing configuration environment variables.")
    for env in missing_envs:
        print(f"  - Please set {env} in your .env file or environment.")
    print("Exiting.")
    sys.exit(1)

# Configure Discord Intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read mention text
intents.members = True          # Required to resolve members & nicknames

bot = discord.Client(intents=intents)
discord_actions.init(bot)
agent = GeminiAgent()

@bot.event
async def on_ready():
    print("=" * 50)
    print(f"Bot successfully logged in as: {bot.user}")
    print(f"Application ID: {bot.user.id}")
    print("=" * 50)
    print("Ready to receive mentions on authorized servers!")

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions

    if is_mentioned or is_dm:
        authorized = False
        if is_dm:
            for guild in message.author.mutual_guilds:
                member = guild.get_member(message.author.id)
                if member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild):
                    authorized = True
                    break
        else:
            author = message.guild.get_member(message.author.id)
            if author and (author.guild_permissions.administrator or author.guild_permissions.manage_guild):
                authorized = True

        if not authorized:
            await message.channel.send("❌ Permission Denied: Only server administrators can command this bot.")
            return

        mention_str = f"<@{bot.user.id}>"
        mention_str_nick = f"<@!{bot.user.id}>"
        prompt = message.content.replace(mention_str, "").replace(mention_str_nick, "").strip()

        if not prompt:
            await message.channel.send(
                f"Hello {message.author.display_name}! I am your Gemini AI Server Manager.\n"
                "Ask me to manage channels, assign roles, kick/ban members, or view server lists."
            )
            return

        context_info = {
            "guild_id": message.guild.id if message.guild else None,
            "channel_id": message.channel.id,
            "author_id": message.author.id,
            "author_name": str(message.author),
        }

        async with message.channel.typing():
            try:
                ai_response = await agent.process_message(prompt, context_info)
                await message.channel.send(ai_response)
            except Exception as e:
                await message.channel.send(f"❌ Failed to process request: {str(e)}")

if __name__ == "__main__":
    bot.run(Config.DISCORD_BOT_TOKEN)
