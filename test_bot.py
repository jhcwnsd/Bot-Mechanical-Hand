import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import discord_actions

class TestDiscordActions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_bot = MagicMock()
        discord_actions.init(self.mock_bot)
        self.guild_id = 123456789
        self.channel_id = 987654321
        self.role_id = 111222333
        self.member_id = 444555666

        # Setup mock guild
        self.mock_guild = MagicMock()
        self.mock_guild.id = self.guild_id
        self.mock_bot.get_guild.return_value = self.mock_guild

    async def test_create_text_channel_success(self):
        # Setup mock channel
        mock_channel = MagicMock()
        mock_channel.name = "general"
        mock_channel.id = self.channel_id
        self.mock_guild.create_text_channel = AsyncMock(return_value=mock_channel)

        result = await discord_actions.create_text_channel(self.guild_id, "general", "General Chat")
        self.mock_guild.create_text_channel.assert_called_once_with(name="general", topic="General Chat")
        self.assertIn("Success", result)
        self.assertIn("general", result)

    async def test_create_text_channel_forbidden(self):
        import discord
        mock_response = MagicMock()
        mock_response.status = 403
        mock_response.reason = "Forbidden"
        self.mock_guild.create_text_channel = AsyncMock(side_effect=discord.Forbidden(mock_response, "Forbidden"))

        result = await discord_actions.create_text_channel(self.guild_id, "general")
        self.assertIn("Error: Bot lacks 'Manage Channels' permission", result)

    async def test_kick_member_success(self):
        mock_member = MagicMock()
        mock_member.name = "JohnDoe"
        mock_member.id = self.member_id
        mock_member.kick = AsyncMock()
        self.mock_guild.get_member.return_value = mock_member

        result = await discord_actions.kick_member(self.guild_id, self.member_id, "Spamming")
        mock_member.kick.assert_called_once_with(reason="Spamming")
        self.assertIn("Success", result)
        self.assertIn("JohnDoe", result)

    async def test_assign_role_success(self):
        mock_member = MagicMock()
        mock_member.display_name = "JaneDoe"
        mock_member.add_roles = AsyncMock()
        
        mock_role = MagicMock()
        mock_role.name = "Moderator"
        
        self.mock_guild.get_member.return_value = mock_member
        self.mock_guild.get_role.return_value = mock_role

        result = await discord_actions.assign_role(self.guild_id, self.member_id, self.role_id)
        mock_member.add_roles.assert_called_once_with(mock_role)
        self.assertIn("Success", result)
        self.assertIn("Moderator", result)

if __name__ == "__main__":
    unittest.main()
