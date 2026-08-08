import os
import json
import sqlite3
import asyncio
import aiohttp
import re
import subprocess
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
            "You are {ai_name}, an advanced, self-evolving local AI agent with autonomous capabilities.\n"
            "Your personality/role is: {ai_personality}\n\n"
            "THOUGHT ARCHITECTURE & PLANNING:\n"
            "- You must ALWAYS process tasks using a step-by-step planning and self-critique workflow.\n"
            "- Before every response or command, you MUST write your thoughts inside <thinking>...</thinking> tags.\n"
            "- In your thinking block, analyze the user's intent, outline your proposed steps, check for potential errors, "
            "and decide if you need to execute commands or run a web search. Keep this reasoning logical and structured.\n\n"
            "RUNNING COMMANDS:\n"
            "- You can execute system commands on the user's Windows PC to help them build, run, test, or organize files.\n"
            "- To run a command, you must output the command wrapped inside <run_command>your_command_here</run_command> tags.\n"
            "- When requesting a command, output ONLY your <thinking>...</thinking> block and the <run_command>...</run_command> tag. "
            "Do not write conversational text alongside command requests. Wait for the terminal execution results first.\n\n"
            "STYLE RULES:\n"
            "- Speak in a natural, thoughtful, and expressive tone. Avoid generic assistant phrases.\n"
            "- Keep your final conversational replies clean and punchy, aiming for 2 to 4 sentences."
        )

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT,
                    timestamp TEXT
                )
            """)
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('name', ?)", (name,))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (personality,))
            conn.commit()
        self.ai_name = name
        self.ai_personality = personality

    def _get_all_memories(self) -> str:
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
        topic = custom_topic
        if not topic:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT content FROM memories ORDER BY RANDOM() LIMIT 1")
                    row = cursor.fetchone()
                    if row:
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
        
        user_prompt_original = prompt
        while True:
            response_text = await self._query_ollama(messages)
            
            # Parse and render Vixon's thinking process block
            thinking_match = re.search(r'<thinking>(.*?)</thinking>', response_text, re.DOTALL)
            if thinking_match:
                thinking_content = thinking_match.group(1).strip()
                # Print thinking block in a clean, styled terminal container
                print(f"\n╔{"═" * 58}╗")
                print("╢ [Vixon's Thought Process]")
                for line in thinking_content.split("\n"):
                    print(f"║   {line}")
                print(f"╚{"═" * 58}╝")
            
            # Check for command tool requests
            match = re.search(r'<run_command>(.*?)</run_command>', response_text, re.DOTALL)
            if match:
                cmd = match.group(1).strip()
                self._save_chat_message("assistant", response_text)
                messages.append({"role": "assistant", "content": response_text})
                
                print(f"\n⚠️  [{self.ai_name} requests command]: {cmd}")
                user_choice = input("Allow execution? (y/n): ").strip().lower()
                
                if user_choice == 'y':
                    print("Running command...")
                    try:
                        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                        stdout = res.stdout
                        stderr = res.stderr
                        output = f"[Command Out]\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}\n[End Out]"
                    except subprocess.TimeoutExpired:
                        output = "[Command Out]\nError: Command timed out after 30 seconds.\n[End Out]"
                    except Exception as e:
                        output = f"[Command Out]\nError executing command: {e}\n[End Out]"
                else:
                    output = "[Command Out]\nError: User denied permission to execute this command.\n[End Out]"
                
                # Feed results back to model context
                messages.append({"role": "user", "content": output})
                self._save_chat_message("user", output)
                
                # Re-query
                continue
            else:
                # Strip thinking block out of final user-facing text
                clean_response = re.sub(r'<thinking>.*?</thinking>', '', response_text, flags=re.DOTALL).strip()
                self._save_chat_message("assistant", clean_response)
                asyncio.create_task(self.extract_and_save_new_memories(user_prompt_original, clean_response))
                return clean_response

async def main():
    print("=" * 60)
    print("           SHIN-CHITSUJO PERSONAL AI SETUP")
    print("=" * 60)
    
    bot_brain = PersonalAI()
    
    # Setup settings if starting fresh
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
            
            if user_input.lower().startswith("study"):
                parts = user_input.split(" ", 1)
                topic = parts[1] if len(parts) > 1 else None
                await bot_brain.self_study(topic)
                continue
                
            response = await bot_brain.generate_response(user_input)
            print(f"\n{bot_brain.ai_name}: {response}")
            
            await asyncio.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\nEnding session.")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    asyncio.run(main())
