import os
from google import genai
from google.genai import types
import discord_actions
from typing import Dict, Any, List

class GeminiAgent:
    def __init__(self):
        # google-genai client handles GEMINI_API_KEY from env automatically
        self.client = genai.Client()
        self.model_name = "gemini-2.5-flash"
        
        # Store conversation history per channel ID
        # Format: Dict[int, List[types.Content]]
        self.chats: Dict[int, List[types.Content]] = {}
        
        self.system_instruction = (
            "You are the server administrator AI for a Discord server. "
            "You have full access to tools that can modify channels, manage permissions, control roles, "
            "mute/ban/kick members, search for members, and send messages.\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. Before calling administrative tools (like kick, ban, create channel), ensure the request came "
            "from an authorized administrator. The Discord client pre-validates this, but you should remain "
            "professional and safe.\n"
            "2. If you need a member's ID, a role's ID, or a channel's ID, check if they are provided in the "
            "context or command. If not, use the `search_members`, `list_roles`, or `list_channels` tools to "
            "find the ID first, then execute the command. Do not guess IDs.\n"
            "3. After invoking a tool, explain what you did clearly in natural language.\n"
            "4. You can call multiple tools sequentially if a request requires multiple actions (e.g. create a role, "
            "then create a private channel using that role)."
        )

    @property
    def tools(self):
        return [
            discord_actions.create_text_channel,
            discord_actions.create_voice_channel,
            discord_actions.delete_channel,
            discord_actions.make_channel_private,
            discord_actions.create_role,
            discord_actions.delete_role,
            discord_actions.assign_role,
            discord_actions.remove_role,
            discord_actions.kick_member,
            discord_actions.ban_member,
            discord_actions.timeout_member,
            discord_actions.untimeout_member,
            discord_actions.send_message_in_channel,
            discord_actions.list_channels,
            discord_actions.list_roles,
            discord_actions.search_members
        ]

    async def process_message(self, prompt: str, context_info: dict) -> str:
        """
        Passes the prompt with guild context to Gemini, coordinates manual tool execution,
        and returns the final AI text response.
        """
        channel_id = context_info["channel_id"]
        
        # Initialize history list for this channel if not exists
        if channel_id not in self.chats:
            self.chats[channel_id] = []
        
        history = self.chats[channel_id]

        # Build context prefix to inform Gemini of the current guild context and request author
        context_prompt = (
            f"[System Guild Context]\n"
            f"- Guild ID: {context_info['guild_id']}\n"
            f"- Channel ID: {context_info['channel_id']}\n"
            f"- Requesting User: {context_info['author_name']} (ID: {context_info['author_id']})\n"
            f"[End Context]\n\n"
            f"User Prompt: {prompt}"
        )

        # Append user message to history
        history.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=context_prompt)]
            )
        )

        # Configure generating config, explicitly disabling automatic function calling to handle async coroutines manually
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            tools=self.tools,
            temperature=0.2, # Low temperature for accurate tool calling
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

        # Call generate content with full history list
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=history,
            config=config
        )

        # Handle potential function calling loops manually
        while response.function_calls:
            # Append the model's turn (containing the function call request) to history
            # response.candidates[0].content contains the model's Content turn
            history.append(response.candidates[0].content)

            print(f"Gemini requested tool execution: {response.function_calls}")
            function_responses = []

            for call in response.function_calls:
                # Find matching function in discord_actions module
                func = getattr(discord_actions, call.name, None)
                if not func:
                    tool_result = f"Error: Tool '{call.name}' not found."
                else:
                    try:
                        # Call the async function with arguments provided by Gemini
                        tool_result = await func(**call.args)
                    except Exception as e:
                        tool_result = f"Exception executing '{call.name}': {str(e)}"
                
                print(f"Tool execution result ({call.name}): {tool_result}")
                
                # Append the function response part to send back
                function_responses.append(
                    types.Part.from_function_response(
                        name=call.name,
                        response={"result": tool_result}
                    )
                )

            # Append the tool execution results as a new turn in history
            history.append(
                types.Content(
                    role="tool",
                    parts=function_responses
                )
            )

            # Request next turn from Gemini with the tool outputs added
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=history,
                config=config
            )

        # Append the final model response (with the text answer) to history
        history.append(response.candidates[0].content)

        # Keep history list under a reasonable size (e.g. keep last 40 turns to prevent token bloat)
        if len(history) > 80:
            history = history[-80:]
            self.chats[channel_id] = history

        return response.text
