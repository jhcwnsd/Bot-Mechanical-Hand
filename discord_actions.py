import discord
from typing import Dict, Any, List, Optional
import datetime

# Global bot reference to prevent SDK serialization from traversing active asyncio objects
_bot: Optional[discord.Client] = None

def init(bot_instance: discord.Client):
    global _bot
    _bot = bot_instance

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
