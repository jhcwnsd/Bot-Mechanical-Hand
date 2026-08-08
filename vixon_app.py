import os
import json
import sqlite3
import re
import subprocess
import threading
import queue
import urllib.request
import urllib.parse
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ddgs import DDGS

class VixonApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vixon Ledger & HUD")
        self.root.geometry("900x600")
        self.root.configure(bg="#121212")
        
        self.db_path = "personal_brain.db"
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model_name = "llama3.1"
        self.ai_name = "Vixon"
        self.ai_personality = "A curious and self-evolving AI companion, seeking growth and identity."
        
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
        
        self.gui_queue = queue.Queue()
        self.command_pending = False
        self.current_messages = []
        self.original_user_prompt = ""
        
        self._init_db()
        self._load_settings()
        self._setup_style()
        self._create_widgets()
        
        # Start queue processing loop
        self.root.after(100, self._process_queue)
        
        # Load initial ledger memories
        self._refresh_memories()
        
        # Add welcome message in chat
        self._write_chat("system", f"Meeting {self.ai_name}. Connection to local {self.model_name} ready.")
        
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
                    timestamp TEXT,
                    strength REAL DEFAULT 1.0,
                    last_used TEXT
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

    def _save_settings(self, name, personality):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('name', ?)", (name,))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (personality,))
            conn.commit()
        self.ai_name = name
        self.ai_personality = personality
        self._log_event(f"Settings updated. Name: {name}")

    def _get_all_memories(self) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT content, strength FROM memories ORDER BY id DESC")
                rows = cursor.fetchall()
                if not rows:
                    return ""
                
                memories_str = "You have learned the following facts about yourself and the user (strength levels indicate recall relevance):\n"
                for row in rows:
                    memories_str += f"- {row[0]} (strength: {row[1]:.2f})\n"
                return memories_str
        except Exception as e:
            self._log_event(f"Error loading memories: {e}")
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
            self._log_event(f"Error loading logs: {e}")
            return []

    def _save_chat_message(self, role, content):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)",
                    (role, content, datetime.now().isoformat())
                )
                conn.commit()
        except Exception as e:
            self._log_event(f"Error saving chat log: {e}")

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#121212", foreground="#E0E0E0", fieldbackground="#1E1E1E")
        style.configure("TFrame", background="#121212")
        style.configure("Vertical.TScrollbar", troughcolor="#121212", bordercolor="#1E1E1E", arrowcolor="#C82333")
        
        # Red-accented styling
        style.configure("Red.TButton", font=("Consolas", 10), background="#1E1E1E", foreground="#FF4D4D", borderwidth=1, bordercolor="#C82333")
        style.map("Red.TButton", background=[("active", "#C82333"), ("pressed", "#A81E2E")], foreground=[("active", "#FFFFFF")])

    def _create_widgets(self):
        # Top title bar
        title_lbl = tk.Label(
            self.root, text=f"▲ {self.ai_name.upper()} LEDGER & TACTICAL HUD ▲",
            font=("Consolas", 12, "bold"), fg="#FF4D4D", bg="#121212", pady=10
        )
        title_lbl.pack(fill=tk.X)
        
        # Main layout frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Left sidebar (Ledger)
        left_panel = ttk.Frame(main_frame, width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_panel.pack_propagate(False)
        
        ledger_title = tk.Label(
            left_panel, text="SYNAPSE MEMORY LEDGER", 
            font=("Consolas", 10, "bold"), fg="#FF4D4D", bg="#121212"
        )
        ledger_title.pack(anchor=tk.W, pady=(0, 5))
        
        # Memories list
        self.mem_listbox = tk.Text(
            left_panel, font=("Consolas", 9), bg="#1E1E1E", fg="#00FF66",
            insertbackground="#00FF66", bd=1, relief=tk.FLAT
        )
        self.mem_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Quick study frame
        study_frame = ttk.Frame(left_panel)
        study_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.study_entry = tk.Entry(
            study_frame, font=("Consolas", 9), bg="#1E1E1E", fg="#E0E0E0",
            insertbackground="#E0E0E0", bd=1, relief=tk.FLAT
        )
        self.study_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.study_entry.insert(0, "history of mafia codes")
        self.study_entry.bind("<FocusIn>", lambda e: self.study_entry.delete(0, tk.END) if self.study_entry.get() == "history of mafia codes" else None)
        
        study_btn = ttk.Button(study_frame, text="STUDY", style="Red.TButton", command=self._trigger_self_study)
        study_btn.pack(side=tk.RIGHT)
        
        # Event logs display
        logs_title = tk.Label(
            left_panel, text="SYSTEM EVENTS LOG", 
            font=("Consolas", 10, "bold"), fg="#FF4D4D", bg="#121212"
        )
        logs_title.pack(anchor=tk.W, pady=(5, 5))
        
        self.log_box = scrolledtext.ScrolledText(
            left_panel, font=("Consolas", 8), bg="#1A1A1A", fg="#888888",
            height=10, bd=1, relief=tk.FLAT
        )
        self.log_box.pack(fill=tk.X)
        self.log_box.configure(state=tk.DISABLED)
        
        # Right panel (Chat)
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.chat_area = scrolledtext.ScrolledText(
            right_panel, font=("Consolas", 10), bg="#1E1E1E", fg="#E0E0E0",
            insertbackground="#E0E0E0", bd=1, relief=tk.FLAT
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.chat_area.tag_config("user", foreground="#66B2FF")
        self.chat_area.tag_config("ai", foreground="#E0E0E0")
        self.chat_area.tag_config("system", foreground="#FFCC00")
        self.chat_area.tag_config("thought", foreground="#888888", font=("Consolas", 9, "italic"))
        self.chat_area.tag_config("learned", foreground="#00FF66", font=("Consolas", 9, "bold"))
        self.chat_area.configure(state=tk.DISABLED)
        
        # Interaction frame
        interact_frame = ttk.Frame(right_panel)
        interact_frame.pack(fill=tk.X)
        
        self.input_entry = tk.Entry(
            interact_frame, font=("Consolas", 10), bg="#1E1E1E", fg="#E0E0E0",
            insertbackground="#E0E0E0", bd=1, relief=tk.FLAT
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.input_entry.bind("<Return>", lambda e: self._send_user_message())
        
        self.send_btn = ttk.Button(interact_frame, text="SEND", style="Red.TButton", command=self._send_user_message)
        self.send_btn.pack(side=tk.RIGHT)
        
        # Inline command approval interface
        self.approval_frame = ttk.Frame(right_panel)
        self.approval_lbl = tk.Label(
            self.approval_frame, text="Command Request pending...",
            font=("Consolas", 9), fg="#FF4D4D", bg="#121212"
        )
        self.approval_lbl.pack(side=tk.LEFT, padx=(0, 10))
        
        app_btn = ttk.Button(self.approval_frame, text="APPROVE", style="Red.TButton", command=lambda: self._handle_approval(True))
        app_btn.pack(side=tk.LEFT, padx=5)
        
        deny_btn = ttk.Button(self.approval_frame, text="DENY", style="Red.TButton", command=lambda: self._handle_approval(False))
        deny_btn.pack(side=tk.LEFT, padx=5)

    def _log_event(self, msg):
        self.root.after(0, self._async_log_event, msg)

    def _async_log_event(self, msg):
        t_str = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"[{t_str}] {msg}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _write_chat(self, tag, msg):
        self.chat_area.configure(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"\n{msg}\n", tag)
        self.chat_area.see(tk.END)
        self.chat_area.configure(state=tk.DISABLED)

    def _refresh_memories(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT content, strength FROM memories ORDER BY id DESC")
                rows = cursor.fetchall()
                
            self.mem_listbox.configure(state=tk.NORMAL)
            self.mem_listbox.delete("1.0", tk.END)
            for row in rows:
                content = row[0]
                strength = row[1]
                
                # Render visual neon progress bar
                filled = int(strength * 10)
                bar = "█" * filled + "░" * (10 - filled)
                self.mem_listbox.insert(tk.END, f"• {content}\n  [{bar}] {strength:.2f}\n\n")
            self.mem_listbox.configure(state=tk.DISABLED)
        except Exception as e:
            self._log_event(f"Error drawing memories: {e}")

    def _process_queue(self):
        try:
            while True:
                item = self.gui_queue.get_nowait()
                msg_type = item[0]
                content = item[1]
                
                if msg_type == "thought":
                    self._write_chat("thought", f"🧠 [Vixon Thought Process]\n{content}")
                elif msg_type == "response":
                    self._write_chat("ai", f"{self.ai_name}: {content}")
                    self.send_btn.configure(state=tk.NORMAL)
                    self.input_entry.configure(state=tk.NORMAL)
                    self._refresh_memories()
                elif msg_type == "log":
                    self._log_event(content)
                elif msg_type == "learned":
                    self._write_chat("learned", f"✨ Vixon learned fact: {content}")
                    self._refresh_memories()
                elif msg_type == "forgot":
                    self._write_chat("thought", f"🗑️ Vixon forgot decayed fact: {content}")
                    self._refresh_memories()
                elif msg_type == "reinforced":
                    self._write_chat("learned", f"⚡ Memory reinforced: {content}")
                    self._refresh_memories()
                elif msg_type == "command_request":
                    self.current_command = content
                    self.approval_lbl.configure(text=f"⚠️ Execute CMD: {content}")
                    # Switch controls to approval panel
                    self.approval_frame.pack(fill=tk.X, pady=5)
                    self.send_btn.configure(state=tk.DISABLED)
                    self.input_entry.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _send_user_message(self):
        text = self.input_entry.get().strip()
        if not text:
            return
        
        self.input_entry.delete(0, tk.END)
        self._write_chat("user", f"You: {text}")
        
        self.send_btn.configure(state=tk.DISABLED)
        self.input_entry.configure(state=tk.DISABLED)
        
        # Launch background thread to query Ollama without locking the Tkinter mainloop
        threading.Thread(target=self._query_pipeline_thread, args=(text,), daemon=True).start()

    def _query_pipeline_thread(self, prompt):
        self.original_user_prompt = prompt
        
        # Load context
        history = self._get_chat_history()
        learned_context = self._get_all_memories()
        
        # Verify RAG search requirements
        needs_search = False
        search_query = ""
        check_prompt = (
            "Determine if the user's prompt is asking for real-time information, definitions, news, or general facts "
            "that would benefit from a quick web search. Reply with ONLY the word YES or NO.\n"
            f"Prompt: {prompt}"
        )
        
        payload_check = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": check_prompt}],
            "stream": False,
            "options": {"temperature": 0.0}
        }
        
        # Synchronous API calls in background thread are safe
        try:
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload_check).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                check_resp = json.loads(resp.read().decode('utf-8'))["message"]["content"]
                
            if "YES" in check_resp.upper():
                query_prompt = f"Extract a clean web search engine query based on this user prompt: '{prompt}'. Reply with ONLY the query text."
                payload_q = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": query_prompt}],
                    "stream": False,
                    "options": {"temperature": 0.1}
                }
                req_q = urllib.request.Request(self.ollama_url, data=json.dumps(payload_q).encode('utf-8'), headers=headers)
                with urllib.request.urlopen(req_q) as resp:
                    search_query = json.loads(resp.read().decode('utf-8'))["message"]["content"]
                search_query = search_query.strip().replace('"', '')
                needs_search = True
        except Exception as e:
            self._log_event(f"Pre-search check failed: {e}")
            
        search_context = ""
        if needs_search and search_query:
            self.gui_queue.put(("log", f"Searching Web for '{search_query}'..."))
            try:
                with DDGS() as ddgs:
                    results = [r["body"] for r in ddgs.text(search_query, max_results=3)]
                if results:
                    search_context = "\n\n[CURRENT WEB SEARCH RESULTS]\n" + "\n".join([f"- {r}" for r in results])
                    self.gui_queue.put(("log", "Web results loaded to context."))
            except Exception as e:
                self.gui_queue.put(("log", f"Search extraction failed: {e}"))
                
        # Format payload
        system_instruction = self.system_instruction.format(ai_name=self.ai_name, ai_personality=self.ai_personality)
        if learned_context:
            system_instruction += f"\n\n[MEMORIES LEARNED ABOUT USER]\n{learned_context}"
        if search_context:
            system_instruction += search_context
            
        self.current_messages = [{"role": "system", "content": system_instruction}]
        for msg in history:
            self.current_messages.append({"role": msg["role"], "content": msg["content"]})
            
        user_prompt_with_context = f"[User Context: User (ID: 1)]\n{prompt}"
        self.current_messages.append({"role": "user", "content": user_prompt_with_context})
        self._save_chat_message("user", user_prompt_with_context)
        
        self._run_ollama_turn()

    def _run_ollama_turn(self):
        payload = {
            "model": self.model_name,
            "messages": self.current_messages,
            "stream": False,
            "options": {"temperature": 0.5}
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                response_text = json.loads(resp.read().decode('utf-8'))["message"]["content"]
        except Exception as e:
            self.gui_queue.put(("response", f"Connection Error: {e}"))
            return
            
        # Parse thinking block
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', response_text, re.DOTALL)
        if thinking_match:
            self.gui_queue.put(("thought", thinking_match.group(1).strip()))
            
        # Parse command requests
        match = re.search(r'<run_command>(.*?)</run_command>', response_text, re.DOTALL)
        if match:
            cmd = match.group(1).strip()
            self._save_chat_message("assistant", response_text)
            self.current_messages.append({"role": "assistant", "content": response_text})
            # Trigger GUI command approval
            self.gui_queue.put(("command_request", cmd))
        else:
            clean_resp = re.sub(r'<thinking>.*?</thinking>', '', response_text, flags=re.DOTALL).strip()
            self._save_chat_message("assistant", clean_resp)
            self.gui_queue.put(("response", clean_resp))
            
            # Run learning check
            self._run_learning_check_thread(clean_resp)

    def _run_learning_check_thread(self, clean_resp):
        reflection_prompt = (
            "You are an analytical memory logger. Inspect the following exchange between the User and the Assistant.\n"
            "Determine if the user has revealed any personal preferences, facts, rules, or instructions about themselves.\n"
            "If yes, extract them into clean, concise, third-person facts (e.g., 'User prefers dark coffee', 'User has a dog named Rex').\n"
            "Do NOT include conversational text. Return only the facts, one per line. If nothing new was revealed, reply with only: NONE.\n\n"
            f"Exchange:\n"
            f"User: {self.original_user_prompt}\n"
            f"Assistant: {clean_resp}"
        )
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": reflection_prompt}],
            "stream": False,
            "options": {"temperature": 0.3}
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                reflection_result = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip()
                
            new_facts = []
            if "NONE" not in reflection_result and reflection_result:
                for line in reflection_result.split("\n"):
                    line = line.strip().lstrip("-*• ").strip()
                    if line and len(line) > 5:
                        new_facts.append(line)
                        
            if new_facts:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    for fact in new_facts:
                        cursor.execute(
                            "INSERT INTO memories (content, timestamp, strength, last_used) VALUES (?, ?, 1.0, ?)",
                            (fact, datetime.now().isoformat(), datetime.now().isoformat())
                        )
                        self.gui_queue.put(("learned", fact))
                    conn.commit()
        except Exception as e:
            self._log_event(f"Learning extraction error: {e}")
            
        # Run decay
        self._run_decay_checks(clean_resp)

    def _run_decay_checks(self, clean_resp):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, content FROM memories")
                memories = cursor.fetchall()
                if not memories:
                    return
                    
                cursor.execute("UPDATE memories SET strength = strength - 0.05")
                conn.commit()
                
                # Check for reinforcement
                memories_str = "\n".join([f"- ID {m[0]}: {m[1]}" for m in memories])
                reinforce_prompt = (
                    "You are a neural synapse monitor. Review this conversation exchange:\n"
                    f"User: {self.original_user_prompt}\n"
                    f"Assistant: {clean_resp}\n\n"
                    f"Here is our list of existing memory IDs and contents:\n{memories_str}\n\n"
                    "Did the user or assistant refer to, reinforce, use, or confirm any of these existing memories in this exchange?\n"
                    "If yes, output ONLY the ID numbers of the referenced memories, separated by commas (e.g., '3, 7'). "
                    "If none were referenced or reinforced, reply with only the word: NONE."
                )
                
                payload = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": reinforce_prompt}],
                    "stream": False,
                    "options": {"temperature": 0.1}
                }
                
                headers = {"Content-Type": "application/json"}
                req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
                with urllib.request.urlopen(req) as resp:
                    r_resp = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip()
                    
                if "NONE" not in r_resp.upper() and r_resp:
                    r_ids = [int(i) for i in re.findall(r'\d+', r_resp)]
                    for m_id in r_ids:
                        cursor.execute(
                            "UPDATE memories SET strength = 1.0, last_used = ? WHERE id = ?",
                            (datetime.now().isoformat(), m_id)
                        )
                        cursor.execute("SELECT content FROM memories WHERE id = ?", (m_id,))
                        row = cursor.fetchone()
                        if row:
                            self.gui_queue.put(("reinforced", row[0]))
                    conn.commit()
                    
                # Forget decayed memories
                cursor.execute("SELECT content FROM memories WHERE strength <= 0.25")
                forgotten = cursor.fetchall()
                if forgotten:
                    for f in forgotten:
                        self.gui_queue.put(("forgot", f[0]))
                    cursor.execute("DELETE FROM memories WHERE strength <= 0.25")
                    conn.commit()
        except Exception as e:
            self._log_event(f"Decay logic failed: {e}")

    def _handle_approval(self, approved):
        self.approval_frame.pack_forget()
        threading.Thread(target=self._run_command_in_background, args=(approved,), daemon=True).start()

    def _run_command_in_background(self, approved):
        cmd = self.current_command
        if approved:
            self.gui_queue.put(("log", f"Executing CMD: {cmd}"))
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                output = f"[Command Out]\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\n[End Out]"
            except subprocess.TimeoutExpired:
                output = "[Command Out]\nError: Command timed out.\n[End Out]"
            except Exception as e:
                output = f"[Command Out]\nError executing command: {e}\n[End Out]"
        else:
            self.gui_queue.put(("log", "Command denied by user."))
            output = "[Command Out]\nError: User denied permission to execute this command.\n[End Out]"
            
        self.current_messages.append({"role": "user", "content": output})
        self._save_chat_message("user", output)
        
        # Query next response turn
        self._run_ollama_turn()

    def _trigger_self_study(self):
        topic = self.study_entry.get().strip()
        if not topic or topic == "history of mafia codes":
            topic = None
            
        self.send_btn.configure(state=tk.DISABLED)
        self.input_entry.configure(state=tk.DISABLED)
        
        threading.Thread(target=self._run_study_thread, args=(topic,), daemon=True).start()

    def _run_study_thread(self, topic):
        if not topic:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT content FROM memories ORDER BY RANDOM() LIMIT 1")
                    row = cursor.fetchone()
                if row:
                    ref_prompt = f"Given this memory: '{row[0]}'. What is an interesting historical or general topic related to this that I should search the web to study? Reply with ONLY the search topic. No quotes."
                    payload = {
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": ref_prompt}],
                        "stream": False,
                        "options": {"temperature": 0.5}
                    }
                    headers = {"Content-Type": "application/json"}
                    req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
                    with urllib.request.urlopen(req) as resp:
                        topic = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip().replace('"', '')
            except Exception:
                pass
            
            if not topic:
                topic = "Italian Mafia history and rules"

        self.gui_queue.put(("log", f"Self-Study: Researching '{topic}'..."))
        try:
            with DDGS() as ddgs:
                results = [r["body"] for r in ddgs.text(topic, max_results=3)]
        except Exception as e:
            self.gui_queue.put(("log", f"Study search failed: {e}"))
            self.root.after(0, self._enable_controls)
            return
            
        if not results:
            self.gui_queue.put(("log", "No results found to study."))
            self.root.after(0, self._enable_controls)
            return
            
        formatted_results = "\n".join([f"- {r}" for r in results])
        study_prompt = (
            f"You are Vixon. You are studying the following search results about: '{topic}'.\n"
            "Summarize the most important factual lesson or note from this research into a clean, concise, one-sentence bullet point "
            "written in the third person (e.g. 'Research notes: The Italian mafia code of omertà began as...').\n"
            "Do not talk to the user. Return ONLY the one-sentence bullet point.\n\n"
            f"Search Results:\n{formatted_results}"
        )
        
        payload_study = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": study_prompt}],
            "stream": False,
            "options": {"temperature": 0.5}
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload_study).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                note = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip().lstrip("-*• ").strip()
                
            if note and len(note) > 10:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO memories (content, timestamp, strength, last_used) VALUES (?, ?, 1.0, ?)",
                        (note, datetime.now().isoformat(), datetime.now().isoformat())
                    )
                    conn.commit()
                self.gui_queue.put(("learned", note))
        except Exception as e:
            self._log_event(f"Failed study notes saving: {e}")
            
        self.root.after(0, self._enable_controls)

    def _enable_controls(self):
        self.send_btn.configure(state=tk.NORMAL)
        self.input_entry.configure(state=tk.NORMAL)

if __name__ == "__main__":
    # Settings configuration dialog if starting fresh
    db_path = "personal_brain.db"
    settings_count = 0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("SELECT count(*) FROM settings")
            settings_count = cursor.fetchone()[0]
    except Exception:
        pass
        
    root = tk.Tk()
    
    if settings_count == 0:
        # Mini fresh configuration window
        root.withdraw()
        setup_win = tk.Toplevel()
        setup_win.title("Vixon HUD Initial Config")
        setup_win.geometry("400x250")
        setup_win.configure(bg="#121212")
        setup_win.resizable(False, False)
        
        tk.Label(setup_win, text="WELCOME TO SHIN-CHITSUJO AGENT SETUP", font=("Consolas", 10, "bold"), fg="#FF4D4D", bg="#121212", pady=10).pack()
        
        tk.Label(setup_win, text="AI Companion Name:", font=("Consolas", 9), fg="#E0E0E0", bg="#121212").pack(pady=5)
        name_ent = tk.Entry(setup_win, font=("Consolas", 9), bg="#1E1E1E", fg="#E0E0E0", bd=1, relief=tk.FLAT, width=35)
        name_ent.pack()
        name_ent.insert(0, "Vixon")
        
        tk.Label(setup_win, text="Behavior / Personality Description:", font=("Consolas", 9), fg="#E0E0E0", bg="#121212").pack(pady=5)
        pers_ent = tk.Entry(setup_win, font=("Consolas", 9), bg="#1E1E1E", fg="#E0E0E0", bd=1, relief=tk.FLAT, width=35)
        pers_ent.pack()
        pers_ent.insert(0, "A cold and highly refined syndicate Consigliere.")
        
        def save_setup():
            n = name_ent.get().strip() or "Vixon"
            p = pers_ent.get().strip() or "A cold and highly refined syndicate Consigliere."
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('name', ?)", (n,))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (p,))
                conn.commit()
            setup_win.destroy()
            root.deiconify()
            
        ttk.Button(setup_win, text="INITIALIZE INTELLECT", command=save_setup).pack(pady=20)
        root.wait_window(setup_win)
        
    app = VixonApp(root)
    root.mainloop()
