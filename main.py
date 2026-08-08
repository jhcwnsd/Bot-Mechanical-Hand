import os
import sys
import discord
from config import Config
import discord_actions
from local_agent import LocalAgent

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
agent = LocalAgent()

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
        allowed_roles = ["♕ 〖 Ruler 〗 ♕", "◈ 〖Undertaker Ruler's Right Hand〗 ◈"]
        if is_dm:
            for guild in bot.guilds:
                member = guild.get_member(message.author.id)
                if member:
                    for role in member.roles:
                        if role.name in allowed_roles:
                            authorized = True
                            break
                if authorized:
                    break
        else:
            author = message.guild.get_member(message.author.id)
            if author:
                for role in author.roles:
                    if role.name in allowed_roles:
                        authorized = True
                        break

        if not authorized:
            await message.channel.send("❌ Permission Denied: You do not have the required role to command this bot.")
            return

        mention_str = f"<@{bot.user.id}>"
        mention_str_nick = f"<@!{bot.user.id}>"
        prompt = message.content.replace(mention_str, "").replace(mention_str_nick, "").strip()

        if not prompt:
            await message.channel.send(
                f"Buonasera, {message.author.display_name}. I am the Consigliere of the Capofamiglia.\n"
                "Tell me, how shall we handle the business of the famiglia today?"
            )
            return

        default_guild_id = bot.guilds[0].id if bot.guilds else None
        context_info = {
            "guild_id": message.guild.id if message.guild else default_guild_id,
            "channel_id": message.channel.id,
            "author_id": message.author.id,
            "author_name": str(message.author),
        }

        async with message.channel.typing():
            try:
                ai_response = await agent.process_message(prompt, context_info)
                await message.channel.send(ai_response)
            except Exception as e:
                err_msg = str(e).upper()
                is_rate_limit = any(term in err_msg for term in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "QUOTA"])
                if is_rate_limit:
                    await message.channel.send("I am tired for today")
                else:
                    await message.channel.send(f"❌ Failed to process request: {str(e)}")

if __name__ == "__main__":
    bot.run(Config.DISCORD_BOT_TOKEN)
