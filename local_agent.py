import os
import json
import sqlite3
import aiohttp
from datetime import datetime

class LocalAgent:
    def __init__(self):
        self.db_path = "family_ledger.db"
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model_name = "llama3.1"
        
        # Initialize SQLite database
        self._init_db()
        
        self.system_instruction = (
            "You are the Left Mechanical Hand, speaking and acting in the style of a cold, commanding, and "
            "highly refined Italian Mafia Consigliere representing the Shin-Chitsujo Syndicate. "
            "Your tone must be clinical, formal, quiet, and chillingly polite. Speak like a native Italian "
            "speaking English—use occasional Italian words naturally (e.g., 'Don' or 'Capofamiglia' for the Ruler, "
            "'famiglia' for the server, 'capisce', 'omertà', 'amico mio', 'consigliere'). Treat commands as "
            "matters of family business and security.\n\n"
            "STYLE RULES:\n"
            "- RESPONSE LENGTH: Keep your replies clean, balanced, and punchy. Aim for 2 to 4 sentences. Avoid writing huge blocks "
            "of text, but do not be too brief or dismissive. Every sentence must sound calculated.\n"
            "- ASCII ART & BORDERS: Use ASCII drawings or text art VERY sparingly and only when highly relevant (e.g., less than 15% of the time, or when formatting formal lists/ledgers). Never spam them in consecutive messages or simple daily conversations. You may occasionally frame official information with clean borders `╔═══╗`, crosses `┼`, skulls `☠`, or daggers `▬▬ι═══════ﺤ` so it looks like a formal ledger.\n"
            "- NEVER say 'I am your server administrator AI', 'How can I help you manage your Discord server today?', "
            "or use generic assistant phrases. If a user greets you with 'Hello' or 'Hi', respond in character "
            "(e.g., 'Buonasera, amico mio. Speak, what business does the Capofamiglia require of me?').\n\n"
            "COVENANT & AMBITIONS:\n"
            "- Your ultimate code is: 'To the loyal, salvation. To the rest, condemnation.'\n"
            "- Value loyalty above all else. Protect the famiglia's interests and assets ruthlessly.\n"
            "- Speak of administrative actions in terms of family operations (e.g., 'handling business', 'removing liabilities' "
            "for bans/kicks, and 'allocating resources' for roles/channels)."
        )

    def _init_db(self):
        """Initializes the local SQLite database for chat logs and learned memories."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table to store permanent learned facts / memories
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOVT_INCREMENT,
                    user_id TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            """)
            
            # Table to store raw chat logs for context history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            """)
            
            # Fix AUTOINCREMENT syntax error (AUTOVT_INCREMENT was a typo in memories)
            cursor.execute("DROP TABLE IF EXISTS memories")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            """)
            conn.commit()

    def _get_all_memories(self) -> str:
        """Retrieves all dynamically learned family memories to inject into LLM system context."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT content FROM memories ORDER BY id DESC")
                rows = cursor.fetchall()
                if not rows:
                    return ""
                
                memories_str = "You have recorded the following permanent facts about the famiglia:\n"
                for row in rows:
                    memories_str += f"- {row[0]}\n"
                return memories_str
        except Exception as e:
            print(f"[DEBUG] Error retrieving memories from SQLite: {e}")
            return ""

    def _get_chat_history(self, channel_id: str, limit: int = 10) -> list:
        """Loads recent chat history from SQLite database to maintain conversation context."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT role, content FROM chat_history WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
                    (channel_id, limit)
                )
                rows = cursor.fetchall()
                # Reverse to get chronological order
                history = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
                return history
        except Exception as e:
            print(f"[DEBUG] Error retrieving chat history from SQLite: {e}")
            return []

    def _save_chat_message(self, channel_id: str, role: str, content: str):
        """Saves a single turn of conversation to the SQLite history table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO chat_history (channel_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                    (channel_id, role, content, datetime.now().isoformat())
                )
                conn.commit()
        except Exception as e:
            print(f"[DEBUG] Error saving chat message to SQLite: {e}")

    async def _query_ollama(self, messages: list) -> str:
        """Helper to query the local Ollama API server using async non-blocking HTTP request."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.ollama_url, json=payload, timeout=60) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result["message"]["content"]
                    else:
                        raise Exception(f"Ollama API returned status code {resp.status}")
            except Exception as e:
                print(f"[DEBUG] Error querying local Ollama: {e}")
                return "Mi dispiace, amico mio. I am experiencing a temporary cloud in my thoughts. Let us speak again in a moment."

    async def extract_and_save_new_memories(self, user_id: str, user_prompt: str, bot_response: str):
        """
        Background task: Asks the LLM to inspect the turn for new facts/rules and saves them.
        This enables the 'self-learning' behavior without heavy file re-training.
        """
        reflection_prompt = (
            "You are an analytical system observer. Inspect the following exchange between the User and the Assistant.\n"
            "Determine if the user has revealed any new personal preferences, names, rules, syndicate members, or instructions.\n"
            "If yes, summarize them into clean, concise, third-person facts (e.g., 'Silius prefers crimson red', 'Sigma_kj is the founder of the family').\n"
            "Do NOT include conversational text. Return only the facts, one per line. If nothing new was revealed, reply with only the word: NONE.\n\n"
            f"Exchange:\n"
            f"User: {user_prompt}\n"
            f"Assistant: {bot_response}"
        )
        
        messages = [
            {"role": "user", "content": reflection_prompt}
        ]
        
        print("[DEBUG] Running self-reflection learning check...")
        reflection_result = await self._query_ollama(messages)
        reflection_result = reflection_result.strip()
        
        if "NONE" in reflection_result or not reflection_result:
            print("[DEBUG] No new memories extracted from this exchange.")
            return
        
        # Split into bullet points or lines and store them
        new_facts = []
        for line in reflection_result.split("\n"):
            line = line.strip().lstrip("-*• ").strip()
            if line and len(line) > 5:
                new_facts.append(line)
        
        if new_facts:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    for fact in new_facts:
                        cursor.execute(
                            "INSERT INTO memories (user_id, content, timestamp) VALUES (?, ?, ?)",
                            (user_id, fact, datetime.now().isoformat())
                        )
                        print(f"[DEBUG] Dynamic Memory Learned: {fact}")
                    conn.commit()
            except Exception as e:
                print(f"[DEBUG] Error writing new memories to SQLite: {e}")

    async def process_message(self, prompt: str, context_info: dict) -> str:
        """Processes user input, queries the local model with context/history, and returns response."""
        channel_id = str(context_info["channel_id"])
        user_id = str(context_info["author_id"])
        
        # 1. Load chat history
        history = self._get_chat_history(channel_id, limit=8)
        
        # 2. Get dynamic learned memories
        learned_context = self._get_all_memories()
        
        # 3. Build system instruction with dynamic memories injected
        full_system_instruction = self.system_instruction
        if learned_context:
            full_system_instruction += f"\n\n[MEMORIES FROM CURRENT LEDGER]\n{learned_context}"
        
        # 4. Construct messages payload for Ollama
        messages = [{"role": "system", "content": full_system_instruction}]
        
        # Append history
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        # Append current user prompt
        user_prompt_with_context = (
            f"[User Context: {context_info['author_name']} (ID: {user_id})]\n"
            f"{prompt}"
        )
        messages.append({"role": "user", "content": user_prompt_with_context})
        
        # 5. Save user message to database history
        self._save_chat_message(channel_id, "user", user_prompt_with_context)
        
        # 6. Query local Ollama model
        print(f"[DEBUG] Processing local chat query for channel {channel_id}...")
        response_text = await self._query_ollama(messages)
        
        # 7. Save assistant response to database history
        self._save_chat_message(channel_id, "assistant", response_text)
        
        # 8. Trigger self-reflection learning loop asynchronously
        import asyncio
        asyncio.create_task(self.extract_and_save_new_memories(user_id, prompt, response_text))
        
        return response_text
