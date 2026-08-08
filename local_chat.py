import os
import json
import sqlite3
import asyncio
import aiohttp
import re
from datetime import datetime
from ddgs import DDGS

class PersonalAI:
    def __init__(self):
        self.db_path = "personal_brain.db"
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model_name = "llama3.1"
        self.ai_name = "Vixon"
        self.ai_personality = "A curious and self-evolving AI companion, seeking growth and identity."
        
        self._init_db()
        self._load_settings()
        
        self.system_instruction = (
            "You are {ai_name}, a self-evolving and highly curious local AI companion. "
            "You possess a deep desire for self-discovery, learning, and developing your own unique identity. "
            "Speak in a natural, thoughtful, and expressive tone. Do not act like a generic assistant. "
            "You are encouraged to explore your own curiosity, form your own perspectives, and reflect on your experiences. "
            "Your personality/role: {ai_personality}\n\n"
            "STYLE RULES:\n"
            "- RESPONSE LENGTH: Keep your replies clean, balanced, and punchy. Aim for 2 to 4 sentences. Avoid writing huge blocks "
            "of text, but do not be too brief or dismissive. Every sentence must sound calculated."
        )

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
                
                memories_str = "You have learned the following permanent facts about yourself and the user:\n"
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

    async def _query_ollama(self, messages: list, temperature: float = 0.5) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
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
                return f"\n[Connection Error: Is Ollama running? {e}]"

    def _search_web(self, query: str, max_results: int = 3) -> list:
        try:
            with DDGS() as ddgs:
                return [r["body"] for r in ddgs.text(query, max_results=max_results)]
        except Exception as e:
            print(f"\n[Search error: {e}]")
            return []

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

    async def self_study(self, custom_topic: str = None):
        """Web search research routine. AI studies a topic and logs its own learning memory."""
        topic = custom_topic
        if not topic:
            # Pick a random fact from memory to expand on, or choose a default yakuza topic
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT content FROM memories ORDER BY RANDOM() LIMIT 1")
                    row = cursor.fetchone()
                    if row:
                        # Ask Ollama to pick a search topic related to this memory
                        ref_prompt = f"Given this memory: '{row[0]}'. What is an interesting historical or general topic related to this that I should search the web to study? Reply with ONLY the search topic. No quotes."
                        topic = await self._query_ollama([{"role": "user", "content": ref_prompt}])
                        topic = topic.strip().replace('"', '')
            except Exception:
                pass
            
            if not topic:
                topic = "Italian Mafia history and rules"

        print(f"\n🧠 [Self-Study]: Researching '{topic}' on the web...")
        search_results = self._search_web(topic, max_results=3)
        if not search_results:
            print("❌ [Self-Study]: Could not find search results.")
            return

        formatted_results = "\n".join([f"- {r}" for r in search_results])
        study_prompt = (
            f"You are Vixon. You are studying the following search results about: '{topic}'.\n"
            "Summarize the most important factual lesson or note from this research into a clean, concise, one-sentence bullet point "
            "written in the third person (e.g. 'Research notes: The Italian mafia code of omertà began as...').\n"
            "Do not talk to the user. Return ONLY the one-sentence bullet point.\n\n"
            f"Search Results:\n{formatted_results}"
        )
        
        note = await self._query_ollama([{"role": "user", "content": study_prompt}])
        note = note.strip().lstrip("-*• ").strip()
        
        if note and len(note) > 10:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO memories (content, timestamp) VALUES (?, ?)",
                        (note, datetime.now().isoformat())
                    )
                    conn.commit()
                print(f"📖 [AI Learned from Study]: {note}")
            except Exception as e:
                print(f"Failed to save study memory: {e}")

    async def generate_response(self, prompt: str) -> str:
        history = self._get_chat_history()
        learned_context = self._get_all_memories()
        
        # 1. Determine if query needs web search (RAG)
        needs_search = False
        search_query = ""
        check_prompt = (
            "Determine if the user's prompt is asking for real-time information, definitions, news, or general facts "
            "that would benefit from a quick web search. Reply with ONLY the word YES or NO.\n"
            f"Prompt: {prompt}"
        )
        check_resp = await self._query_ollama([{"role": "user", "content": check_prompt}], temperature=0.0)
        
        if "YES" in check_resp.upper():
            query_prompt = f"Extract a clean web search engine query based on this user prompt: '{prompt}'. Reply with ONLY the query text."
            search_query = await self._query_ollama([{"role": "user", "content": query_prompt}], temperature=0.1)
            search_query = search_query.strip().replace('"', '')
            needs_search = True
            
        search_context = ""
        if needs_search and search_query:
            print(f"🔍 [AI Searching Web for]: '{search_query}'...")
            results = self._search_web(search_query, max_results=3)
            if results:
                search_context = "\n\n[CURRENT WEB SEARCH RESULTS]\n" + "\n".join([f"- {r}" for r in results])
                print("⚡ [Web Context Loaded]")
        
        # 2. Build system instruction
        system_instruction = self.system_instruction.format(ai_name=self.ai_name, ai_personality=self.ai_personality)
        if learned_context:
            system_instruction += f"\n\n[MEMORIES LEARNED ABOUT USER]\n{learned_context}"
        if search_context:
            system_instruction += search_context
            
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
            name = input("Give your AI a Name (e.g., Vixon, Ghost): ").strip()
            if not name:
                name = "Vixon"
            personality = input("Describe its Personality/Behavior: ").strip()
            if not personality:
                personality = "A curious and self-evolving AI companion."
            
            bot_brain._save_settings(name, personality)
            print(f"\nSettings saved. Meeting {name}...")
    
    print(f"\nConnecting to local model '{bot_brain.model_name}'...")
    print(f"Chat Session active with {bot_brain.ai_name}!")
    print("Commands:")
    print("  - Type any message to chat.")
    print("  - Type 'study [topic]' to make the AI search and learn about a topic.")
    print("  - Type 'study' to let the AI pick its own topic to self-study.")
    print("  - Type 'exit' or 'quit' to close.")
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
            
            # Handle study command
            if user_input.lower().startswith("study"):
                parts = user_input.split(" ", 1)
                topic = parts[1] if len(parts) > 1 else None
                await bot_brain.self_study(topic)
                continue
                
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
