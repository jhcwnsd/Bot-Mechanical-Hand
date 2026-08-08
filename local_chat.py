import os
import json
import sqlite3
import asyncio
import aiohttp
from datetime import datetime

class PersonalAI:
    def __init__(self):
        self.db_path = "personal_brain.db"
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model_name = "llama3.1"
        self.ai_name = "Assistant"
        self.ai_personality = "A helpful, friendly AI companion."
        
        self._init_db()
        self._load_settings()

    def _init_db(self):
        # Create database for custom AI settings, memories, and chat logs
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table for name/personality settings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # Table to store permanent learned facts / memories
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT,
                    timestamp TEXT
                )
            """)
            
            # Table to store chat history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            """)
            conn.commit()

    def _load_settings(self):
        # Load AI name and personality from database if they exist
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'name'")
            name_row = cursor.fetchone()
            cursor.execute("SELECT value FROM settings WHERE key = 'personality'")
            pers_row = cursor.fetchone()
            
            if name_row:
                self.ai_name = name_row[0]
            if pers_row:
                self.ai_personality = pers_row[0]

    def _save_settings(self, name: str, personality: str):
        # Save settings to database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('name', ?)", (name,))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (personality,))
            conn.commit()
        self.ai_name = name
        self.ai_personality = personality

    def _get_all_memories(self) -> str:
        # Load learned facts
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT content FROM memories ORDER BY id DESC")
                rows = cursor.fetchall()
                if not rows:
                    return ""
                
                memories_str = "You have learned the following permanent facts about the user:\n"
                for row in rows:
                    memories_str += f"- {row[0]}\n"
                return memories_str
        except Exception as e:
            print(f"Error loading memories: {e}")
            return ""

    def _get_chat_history(self, limit: int = 15) -> list:
        # Load context logs
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
        except Exception as e:
            print(f"Error loading logs: {e}")
            return []

    def _save_chat_message(self, role: str, content: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)",
                    (role, content, datetime.now().isoformat())
                )
                conn.commit()
        except Exception as e:
            print(f"Error saving chat log: {e}")

    async def _query_ollama(self, messages: list) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.5
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.ollama_url, json=payload, timeout=60) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result["message"]["content"]
                    else:
                        raise Exception(f"Ollama returned error: {resp.status}")
            except Exception as e:
                return f"\n[Connection Error: Is Ollama running in your taskbar? {e}]"

    async def extract_and_save_new_memories(self, user_prompt: str, bot_response: str):
        reflection_prompt = (
            "You are an analytical memory logger. Inspect the following exchange between the User and the Assistant.\n"
            "Determine if the user has revealed any personal preferences, facts, rules, or instructions about themselves.\n"
            "If yes, extract them into clean, concise, third-person facts (e.g., 'User prefers dark coffee', 'User has a dog named Rex').\n"
            "Do NOT include conversational text. Return only the facts, one per line. If nothing new was revealed, reply with only: NONE.\n\n"
            f"Exchange:\n"
            f"User: {user_prompt}\n"
            f"Assistant: {bot_response}"
        )
        
        messages = [{"role": "user", "content": reflection_prompt}]
        reflection_result = await self._query_ollama(messages)
        reflection_result = reflection_result.strip()
        
        if "NONE" in reflection_result or not reflection_result:
            return
        
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
                            "INSERT INTO memories (content, timestamp) VALUES (?, ?)",
                            (fact, datetime.now().isoformat())
                        )
                        print(f"\n✨ [AI Learned]: {fact}")
                    conn.commit()
            except Exception as e:
                print(f"Memory save error: {e}")

    async def generate_response(self, prompt: str) -> str:
        history = self._get_chat_history()
        learned_context = self._get_all_memories()
        
        # Build system instruction
        system_instruction = (
            f"You are {self.ai_name}.\n"
            f"Your personality/role is: {self.ai_personality}\n\n"
        )
        if learned_context:
            system_instruction += f"[MEMORIES LEARNED ABOUT USER]\n{learned_context}"
            
        messages = [{"role": "system", "content": system_instruction}]
        
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        messages.append({"role": "user", "content": prompt})
        
        self._save_chat_message("user", prompt)
        response_text = await self._query_ollama(messages)
        self._save_chat_message("assistant", response_text)
        
        # Trigger background learning
        asyncio.create_task(self.extract_and_save_new_memories(prompt, response_text))
        
        return response_text

async def main():
    print("=" * 60)
    print("           SHIN-CHITSUJO PERSONAL AI SETUP")
    print("=" * 60)
    
    bot_brain = PersonalAI()
    
    # Setup name and personality if starting fresh
    with sqlite3.connect(bot_brain.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            print("\nStarting fresh. Let's design your custom AI:")
            name = input("Give your AI a Name (e.g., Leo, Sophia, Ghost): ").strip()
            if not name:
                name = "Companion"
            personality = input("Describe its Personality/Behavior: ").strip()
            if not personality:
                personality = "A friendly AI companion."
            
            bot_brain._save_settings(name, personality)
            print(f"\nSettings saved. Meeting {name}...")
    
    print(f"\nConnecting to local model '{bot_brain.model_name}'...")
    print(f"Chat Session active with {bot_brain.ai_name}!")
    print("Type 'exit' or 'quit' to close the chat.")
    print("-" * 60)
    
    # Print existing learned facts
    existing_memories = bot_brain._get_all_memories()
    if existing_memories:
        print(f"\n[Persisted Memory Ledger]\n{existing_memories}")
        print("-" * 60)
        
    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("Ending chat session. Buonanotte.")
                break
                
            response = await bot_brain.generate_response(user_input)
            print(f"\n{bot_brain.ai_name}: {response}")
            
            # Small delay to let background tasks print output cleanly
            await asyncio.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\nEnding session.")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    asyncio.run(main())
