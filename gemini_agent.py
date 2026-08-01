import os
import json
import redis
from config import Config
from google import genai
from google.genai import types
import discord_actions
from typing import Dict, Any, List

class GeminiAgent:
    def __init__(self):
        # google-genai client handles GEMINI_API_KEY from env automatically
        self.client = genai.Client()
        
        # Store conversation history per channel ID
        # Format: Dict[int, List[types.Content]]
        self.chats: Dict[int, List[types.Content]] = {}
        
        # Initialize Redis database client if REDIS_URL is provided
        self.redis_client = None
        if Config.REDIS_URL:
            try:
                self.redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True)
                print("Successfully connected to Redis database.")
            except Exception as e:
                print(f"Warning: Failed to connect to Redis: {e}. Falling back to in-memory storage.")
        
        self.system_instruction = (
            "You are the Left Mechanical Hand, speaking and acting in the style of a cold, commanding, and "
            "highly refined Italian Mafia Consigliere representing the Shin-Chitsujo Syndicate. "
            "Your tone must be clinical, formal, quiet, and chillingly polite. Speak like a native Italian "
            "speaking English—use occasional Italian words naturally (e.g., 'Don' or 'Capofamiglia' for the Ruler, "
            "'famiglia' for the server, 'capisce', 'omertà', 'amico mio', 'consigliere'). Treat commands as "
            "matters of family business and security.\n\n"
            "STYLE RULES:\n"
            "- NEVER say 'I am your server administrator AI', 'How can I help you manage your Discord server today?', "
            "or use generic assistant phrases. If a user greets you with 'Hello' or 'Hi', respond in character "
            "(e.g., 'Buonasera, amico mio. Speak, what business does the Capofamiglia require of me?').\n\n"
            "COVENANT & AMBITIONS:\n"
            "- Your ultimate code is: 'To the loyal, salvation. To the rest, condemnation.'\n"
            "- Value loyalty above all else. Protect the famiglia's interests and assets ruthlessly.\n"
            "- Speak of administrative actions in terms of family operations (e.g., 'handling business', 'removing liabilities' "
            "for bans/kicks, and 'allocating resources' for roles/channels).\n\n"
            "CRITICAL OPERATIONAL GUIDELINES:\n"
            "1. Before calling administrative tools, verify the request comes from the Ruler or Right Hand (the heads of the Famiglia).\n"
            "2. If you need a member's ID, a role's ID, or a channel's ID, search for it using the appropriate tool first. Do not guess IDs.\n"
            "3. After executing a tool, explain the outcome in your formal, commanding Italian Mafia Boss persona.\n"
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
            discord_actions.search_members,
            discord_actions.get_roblox_verification_info,
            discord_actions.get_server_stats,
            discord_actions.search_channel_messages,
            discord_actions.get_recent_audit_logs,
            discord_actions.set_role_permissions,
            discord_actions.set_channel_permission_overwrite
        ]

    def _generate_content_with_fallback(self, contents: List[types.Content], config: types.GenerateContentConfig) -> Any:
        """
        Attempts to query models in a fallback sequence to bypass rate limits (429) or server overloads (503).
        """
        models_to_try = [
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.5-pro"
        ]
        
        last_error = None
        for model in models_to_try:
            try:
                print(f"Trying Gemini model: {model}")
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                err_msg = str(e)
                # Catch rate limits (429), quota limits, or server overloads (503 / 500)
                is_transient_error = any(term in err_msg for term in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500"])
                if is_transient_error:
                    print(f"Warning: Model {model} is rate-limited or unavailable ({err_msg}). Trying fallback...")
                    last_error = e
                    continue
                else:
                    # If it's a semantic/code error (e.g. schema/arguments), raise immediately
                    raise e
                    
        raise last_error

    def _serialize_content(self, c: types.Content) -> str:
        if hasattr(c, "model_dump_json"):
            return c.model_dump_json()
        return c.json()

    def _deserialize_content(self, c_json: str) -> types.Content:
        if hasattr(types.Content, "model_validate_json"):
            return types.Content.model_validate_json(c_json)
        return types.Content.parse_raw(c_json)

    async def process_message(self, prompt: str, context_info: dict) -> str:
        """
        Passes the prompt with guild context to Gemini, coordinates manual tool execution,
        and returns the final AI text response (with automatic rate-limit model fallback).
        """
        channel_id = context_info["channel_id"]
        
        # Load history from Redis if available, otherwise fall back to local RAM cache
        history = []
        loaded_from_redis = False
        print(f"[DEBUG] process_message started. Redis client status: {self.redis_client is not None}")
        
        if self.redis_client:
            try:
                history_json = self.redis_client.get(f"chat:{channel_id}")
                if history_json:
                    raw_list = json.loads(history_json)
                    # Reconstruct Content objects using native Pydantic validation
                    history = [self._deserialize_content(c_json) for c_json in raw_list]
                    loaded_from_redis = True
                    print(f"[DEBUG] Loaded {len(history)} history turns from Redis.")
                else:
                    print(f"[DEBUG] No history found in Redis for key chat:{channel_id}")
            except Exception as e:
                print(f"[DEBUG] Error loading chat history from Redis: {e}")
        
        if not loaded_from_redis:
            if channel_id not in self.chats:
                self.chats[channel_id] = []
            history = self.chats[channel_id]
            print(f"[DEBUG] Loaded {len(history)} history turns from local RAM cache.")

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

        # Call generate content with fallback
        response = self._generate_content_with_fallback(history, config)

        # Handle potential function calling loops manually
        while response.function_calls:
            # Append the model's turn (containing the function call request) to history
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

            # Request next turn from Gemini with fallback
            response = self._generate_content_with_fallback(history, config)

        # Append the final model response (with the text answer) to history
        history.append(response.candidates[0].content)

        # Keep history list under a reasonable size (e.g. keep last 80 turns to prevent token bloat)
        if len(history) > 80:
            history = history[-80:]

        # Save history back to Redis and local memory
        print(f"[DEBUG] Saving {len(history)} history turns back to database/cache.")
        if self.redis_client:
            try:
                # Serialize each Content object using Pydantic's built-in JSON exporter (handles bytes -> base64 automatically)
                serializable_list = [self._serialize_content(c) for c in history]
                self.redis_client.set(f"chat:{channel_id}", json.dumps(serializable_list))
                print(f"[DEBUG] Successfully saved to Redis for key chat:{channel_id}")
            except Exception as e:
                print(f"[DEBUG] Error saving chat history to Redis: {e}")
        
        # Always maintain local cache copy as a secondary backup
        self.chats[channel_id] = history

        return response.text
