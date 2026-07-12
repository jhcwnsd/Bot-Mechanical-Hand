import discord
from typing import Dict, Any, List, Optional
import datetime
import aiohttp

# Global bot reference to prevent SDK serialization from traversing active asyncio objects
_bot: Optional[discord.Client] = None

def init(bot_instance: discord.Client):
    global _bot
    _bot = bot_instance

async def get_roblox_verification_info(discord_id: str) -> str:
    """
    Fetches the Roblox username, Roblox ID, profile description, and account creation date 
    linked to a Discord ID using the public RoVer registry API and official Roblox API.
    
    Args:
        discord_id: The Discord ID of the user to look up.
    """
    if not _bot:
        return "Error: Bot not initialized."
    
    # Strip any mention tags if passed
    discord_id_clean = discord_id.replace("<@", "").replace(">", "").replace("!", "").strip()
    
    try:
        url = f"https://registry.rover.link/v2/discord-to-roblox/{discord_id_clean}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                if resp.status == 404:
                    return f"This user (Discord ID: {discord_id_clean}) is not verified with RoVer."
                elif resp.status != 200:
                    return f"Error: RoVer API returned status code {resp.status}."
                data = await resp.json()
                
        roblox_id = data.get("robloxId")
        roblox_username = data.get("robloxUsername")
        if not roblox_id:
            return "Could not find a linked Roblox ID for this user."
            
        # Query Roblox official API to get display name, description, creation date
        user_url = f"https://users.roblox.com/v1/users/{roblox_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(user_url) as resp:
                if resp.status == 200:
                    user_data = await resp.json()
                    description = user_data.get("description", "No description set")
                    created_raw = user_data.get("created", "")
                    created_date = created_raw.split("T")[0] if created_raw else "Unknown"
                    display_name = user_data.get("displayName", "")
                else:
                    description = "N/A"
                    created_date = "N/A"
                    display_name = "N/A"
                    
        return (
            f"**Linked Roblox Account Information:**\n"
            f"- **Username:** {roblox_username}\n"
            f"- **Display Name:** {display_name}\n"
            f"- **Roblox ID:** `{roblox_id}`\n"
            f"- **Account Created:** {created_date}\n"
            f"- **Profile Description:** \"{description}\"\n"
            f"- **Profile Link:** <https://www.roblox.com/users/{roblox_id}/profile>"
        )
        
    except Exception as e:
        return f"Error fetching Roblox details: {str(e)}"

async def get_server_stats(guild_id: str) -> str:
    """
    Retrieves real-time server stats including member count, active status, boosts, and channel counts.
    
    Args:
        guild_id: The ID of the guild (server) as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return "Error: Guild not found."

    total_members = guild.member_count
    # Calculate online/offline if members intent is enabled and cached
    online = sum(1 for m in guild.members if m.status != discord.Status.offline)
    bot_count = sum(1 for m in guild.members if m.bot)
    human_count = total_members - bot_count
    
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    roles_count = len(guild.roles)
    
    boost_count = guild.premium_subscription_count
    boost_tier = guild.premium_tier
    
    created_at = guild.created_at.strftime("%Y-%m-%d")

    return (
        f"📊 **Server Statistics for {guild.name}:**\n"
        f"- **Total Members:** {total_members} ({human_count} humans, {bot_count} bots)\n"
        f"- **Estimated Online Members:** {online}\n"
        f"- **Boost Tier:** Tier {boost_tier} ({boost_count} boosts)\n"
        f"- **Channels:** {text_channels} text, {voice_channels} voice, {categories} categories\n"
        f"- **Total Roles:** {roles_count}\n"
        f"- **Created On:** {created_at}\n"
        f"- **Server Owner ID:** `{guild.owner_id}`"
    )

async def search_channel_messages(guild_id: str, channel_id: str, query: str, limit: int = 25) -> str:
    """
    Searches recent message history in a channel for specific keywords to help answer questions.
    
    Args:
        guild_id: The ID of the guild.
        channel_id: The ID of the channel to search.
        query: The keyword to search for in message content (case-insensitive).
        limit: Max number of recent messages to check (default 25, max 100).
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        channel = guild.get_channel(int(channel_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not channel or not isinstance(channel, discord.TextChannel):
        return "Error: Text channel not found."

    limit = min(max(1, limit), 100)
    matches = []
    
    try:
        async for message in channel.history(limit=limit):
            if query.lower() in message.content.lower():
                created = message.created_at.strftime("%Y-%m-%d %H:%M")
                matches.append(f"[{created}] {message.author.display_name}: {message.content}")
                
        if not matches:
            return f"No messages containing '{query}' found in recent {limit} messages of #{channel.name}."
            
        header = f"🔍 Found {len(matches)} matching messages in #{channel.name} (searching last {limit} messages):\n"
        return header + "\n".join(matches[:15])
    except discord.Forbidden:
        return f"Error: Bot lacks permission to read history in #{channel.name}."
    except Exception as e:
        return f"Error: {str(e)}"

async def get_recent_audit_logs(guild_id: str, limit: int = 5) -> str:
    """
    Retrieves the most recent audit log actions (e.g. bans, kicks, channel changes) done on the server.
    
    Args:
        guild_id: The ID of the guild.
        limit: Number of audit logs to retrieve (default 5, max 20).
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return "Error: Guild not found."

    limit = min(max(1, limit), 20)
    lines = ["📋 **Recent Audit Logs:**"]
    
    try:
        async for entry in guild.audit_logs(limit=limit):
            action = str(entry.action).replace("AuditLogAction.", "")
            user = entry.user.display_name if entry.user else "Unknown"
            target = str(entry.target)
            created = entry.created_at.strftime("%Y-%m-%d %H:%M")
            reason = f" (Reason: {entry.reason})" if entry.reason else ""
            lines.append(f"- [{created}] **{user}** performed **{action}** on **{target}**{reason}")
            
        return "\n".join(lines)
    except discord.Forbidden:
        return "Error: Bot lacks permission to view audit logs (requires 'View Audit Log' permission)."
    except Exception as e:
        return f"Error: {str(e)}"

async def create_text_channel(guild_id: str, channel_name: str, topic: Optional[str] = None) -> str:
    """
    Creates a new text channel in the server.
    
    Args:
        guild_id: The ID of the guild (server) as a string (to prevent float rounding issues).
        channel_name: The name of the new text channel.
        topic: Optional description or topic of the channel.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return f"Error: Invalid guild ID '{guild_id}'."
        
    if not guild:
        return f"Error: Guild with ID {guild_id} not found."
    
    try:
        channel = await guild.create_text_channel(name=channel_name, topic=topic)
        return f"Success: Created text channel '{channel.name}' (ID: {channel.id})."
    except discord.Forbidden:
        return "Error: Bot lacks 'Manage Channels' permission."
    except Exception as e:
        return f"Error: {str(e)}"

async def create_voice_channel(guild_id: str, channel_name: str) -> str:
    """
    Creates a new voice channel in the server.
    
    Args:
        guild_id: The ID of the guild (server) as a string.
        channel_name: The name of the new voice channel.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return f"Error: Invalid guild ID '{guild_id}'."
        
    if not guild:
        return f"Error: Guild with ID {guild_id} not found."
    
    try:
        channel = await guild.create_voice_channel(name=channel_name)
        return f"Success: Created voice channel '{channel.name}' (ID: {channel.id})."
    except discord.Forbidden:
        return "Error: Bot lacks 'Manage Channels' permission."
    except Exception as e:
        return f"Error: {str(e)}"

async def delete_channel(guild_id: str, channel_id: str, reason: Optional[str] = None) -> str:
    """
    Deletes a channel (text or voice) from the server.
    
    Args:
        guild_id: The ID of the guild as a string.
        channel_id: The ID of the channel to delete as a string.
        reason: Optional reason for deletion.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return "Error: Guild not found."
    
    try:
        channel = guild.get_channel(int(channel_id))
    except ValueError:
        return "Error: Invalid channel ID."
        
    if not channel:
        return f"Error: Channel with ID {channel_id} not found."
    
    try:
        await channel.delete(reason=reason)
        return f"Success: Deleted channel '{channel.name}'."
    except discord.Forbidden:
        return "Error: Bot lacks 'Manage Channels' permission."
    except Exception as e:
        return f"Error: {str(e)}"

async def make_channel_private(guild_id: str, channel_id: str, role_id: str) -> str:
    """
    Makes a channel private so that only a specific role can view it.
    
    Args:
        guild_id: The ID of the guild as a string.
        channel_id: The ID of the channel as a string.
        role_id: The ID of the role that is allowed to view the channel as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        channel = guild.get_channel(int(channel_id)) if guild else None
        role = guild.get_role(int(role_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not channel or not role:
        return "Error: Guild, Channel, or Role not found."
    
    try:
        everyone = guild.default_role
        overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True)
        }
        await channel.edit(overwrites=overwrites)
        return f"Success: Channel '{channel.name}' is now private for role '{role.name}'."
    except discord.Forbidden:
        return "Error: Bot lacks 'Manage Roles' or 'Manage Channels' permission."
    except Exception as e:
        return f"Error: {str(e)}"

async def create_role(guild_id: str, role_name: str, color_hex: Optional[str] = None) -> str:
    """
    Creates a new role in the server.
    
    Args:
        guild_id: The ID of the guild as a string.
        role_name: The name of the new role.
        color_hex: Optional hex color code (e.g. 'ff0000' for red).
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return "Error: Guild not found."
    
    color = discord.Color.default()
    if color_hex:
        try:
            color = discord.Color(int(color_hex.lstrip('#'), 16))
        except ValueError:
            pass

    try:
        role = await guild.create_role(name=role_name, color=color)
        return f"Success: Created role '{role.name}' (ID: {role.id})."
    except discord.Forbidden:
        return "Error: Bot lacks 'Manage Roles' permission."
    except Exception as e:
        return f"Error: {str(e)}"

async def delete_role(guild_id: str, role_id: str) -> str:
    """
    Deletes a role from the server.
    
    Args:
        guild_id: The ID of the guild as a string.
        role_id: The ID of the role to delete as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        role = guild.get_role(int(role_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not role:
        return "Error: Guild or Role not found."

    try:
        await role.delete()
        return f"Success: Deleted role '{role.name}'."
    except discord.Forbidden:
        return "Error: Bot lacks permission or the role is higher than the bot's role."
    except Exception as e:
        return f"Error: {str(e)}"

async def assign_role(guild_id: str, member_id: str, role_id: str) -> str:
    """
    Assigns a role to a member.
    
    Args:
        guild_id: The ID of the guild as a string.
        member_id: The ID of the member as a string.
        role_id: The ID of the role to assign as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        member = guild.get_member(int(member_id)) if guild else None
        role = guild.get_role(int(role_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not member or not role:
        return "Error: Guild, Member, or Role not found."

    try:
        await member.add_roles(role)
        return f"Success: Assigned role '{role.name}' to {member.display_name}."
    except discord.Forbidden:
        return "Error: Bot lacks permissions or the role is higher than the bot's role."
    except Exception as e:
        return f"Error: {str(e)}"

async def remove_role(guild_id: str, member_id: str, role_id: str) -> str:
    """
    Removes a role from a member.
    
    Args:
        guild_id: The ID of the guild as a string.
        member_id: The ID of the member as a string.
        role_id: The ID of the role to remove as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        member = guild.get_member(int(member_id)) if guild else None
        role = guild.get_role(int(role_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not member or not role:
        return "Error: Guild, Member, or Role not found."

    try:
        await member.remove_roles(role)
        return f"Success: Removed role '{role.name}' from {member.display_name}."
    except discord.Forbidden:
        return "Error: Bot lacks permissions or the role is higher than the bot's role."
    except Exception as e:
        return f"Error: {str(e)}"

async def kick_member(guild_id: str, member_id: str, reason: Optional[str] = None) -> str:
    """
    Kicks a member from the server.
    
    Args:
        guild_id: The ID of the guild as a string.
        member_id: The ID of the member to kick as a string.
        reason: Optional reason for the kick.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        member = guild.get_member(int(member_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not member:
        return "Error: Guild or Member not found."

    try:
        await member.kick(reason=reason)
        return f"Success: Kicked member {member.name} (Reason: {reason})."
    except discord.Forbidden:
        return "Error: Bot lacks permissions or member has a higher role."
    except Exception as e:
        return f"Error: {str(e)}"

async def ban_member(guild_id: str, member_id: str, reason: Optional[str] = None) -> str:
    """
    Bans a member from the server.
    
    Args:
        guild_id: The ID of the guild as a string.
        member_id: The ID of the member to ban as a string.
        reason: Optional reason for the ban.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        member = guild.get_member(int(member_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not member:
        return "Error: Guild or Member not found."

    try:
        await member.ban(reason=reason)
        return f"Success: Banned member {member.name} (Reason: {reason})."
    except discord.Forbidden:
        return "Error: Bot lacks permissions or member has a higher role."
    except Exception as e:
        return f"Error: {str(e)}"

async def timeout_member(guild_id: str, member_id: str, duration_minutes: int, reason: Optional[str] = None) -> str:
    """
    Temporarily times out (mutes) a member so they cannot send messages or talk in voice channels.
    
    Args:
        guild_id: The ID of the guild as a string.
        member_id: The ID of the member to timeout as a string.
        duration_minutes: The duration of the timeout in minutes.
        reason: Optional reason for timing out the member.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        member = guild.get_member(int(member_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not member:
        return "Error: Guild or Member not found."

    try:
        duration = datetime.timedelta(minutes=duration_minutes)
        await member.timeout(duration, reason=reason)
        return f"Success: Timed out {member.name} for {duration_minutes} minutes."
    except discord.Forbidden:
        return "Error: Bot lacks permissions or member has a higher role."
    except Exception as e:
        return f"Error: {str(e)}"

async def untimeout_member(guild_id: str, member_id: str) -> str:
    """
    Removes timeout restriction from a member.
    
    Args:
        guild_id: The ID of the guild as a string.
        member_id: The ID of the member as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        member = guild.get_member(int(member_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not member:
        return "Error: Guild or Member not found."

    try:
        await member.timeout(None)
        return f"Success: Removed timeout restriction from {member.name}."
    except discord.Forbidden:
        return "Error: Bot lacks permissions or member has a higher role."
    except Exception as e:
        return f"Error: {str(e)}"

async def send_message_in_channel(guild_id: str, channel_id: str, content: str) -> str:
    """
    Sends a text message to a specific channel.
    
    Args:
        guild_id: The ID of the guild as a string.
        channel_id: The ID of the target channel as a string.
        content: The text content of the message to send.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
        channel = guild.get_channel(int(channel_id)) if guild else None
    except ValueError:
        return "Error: Invalid ID provided."
        
    if not guild or not channel or not isinstance(channel, discord.TextChannel):
        return f"Error: Text channel with ID {channel_id} not found."
    
    try:
        await channel.send(content)
        return f"Success: Sent message in '{channel.name}'."
    except discord.Forbidden:
        return f"Error: Bot cannot write in channel {channel.name}."
    except Exception as e:
        return f"Error: {str(e)}"
            
async def list_channels(guild_id: str) -> str:
    """
    Lists all text and voice channels in the guild, returning names and IDs.
    
    Args:
        guild_id: The ID of the guild as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return f"Error: Guild with ID {guild_id} not found."
    
    lines = ["Current Channels:"]
    for c in guild.channels:
        lines.append(f"- #{c.name} (ID: {c.id}, Type: {c.type})")
    return "\n".join(lines)

async def list_roles(guild_id: str) -> str:
    """
    Lists all roles in the server, returning names and IDs.
    
    Args:
        guild_id: The ID of the guild as a string.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return "Error: Guild not found."
    
    lines = ["Current Roles:"]
    for r in guild.roles:
        lines.append(f"- {r.name} (ID: {r.id})")
    return "\n".join(lines)

async def search_members(guild_id: str, query: str) -> str:
    """
    Searches for server members by display name or username to resolve their IDs.
    
    Args:
        guild_id: The ID of the guild as a string.
        query: The name prefix or query to search for.
    """
    if not _bot:
        return "Error: Bot not initialized."
    try:
        guild = _bot.get_guild(int(guild_id))
    except ValueError:
        return "Error: Invalid guild ID."
        
    if not guild:
        return "Error: Guild not found."
    
    matches = []
    for member in guild.members:
        if query.lower() in member.name.lower() or query.lower() in member.display_name.lower():
            matches.append(f"- {member.name} / {member.display_name} (ID: {member.id})")
    
    if not matches:
        return f"No members found matching query '{query}'."
    return "\n".join(matches[:15])
