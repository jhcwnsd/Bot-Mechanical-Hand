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
import customtkinter as ctk
from ddgs import DDGS

# Set theme and color options
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class VixonApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vixon Ledger & Tactical HUD")
        self.root.geometry("950x650")
        self.root.configure(bg="#0B0B0C")
        
        self.db_path = "personal_brain.db"
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model_name = "llama3.1"
        self.ai_name = "Vixon"
        self.ai_personality = "A cold, highly refined syndicate Consigliere representing the Shin-Chitsujo Syndicate."
        
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
        self._create_widgets()
        
        # Start queue reader loop
        self.root.after(100, self._process_queue)
        
        # Initial draw of memories
        self._refresh_memories()
        
        # Welcoming print
        self._write_chat("system", f"Meeting {self.ai_name}. Connection to local {self.model_name} active.")
        
    def _init_db(self):
        # Database table creations and schema checks
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
            
            # Explicit column check and migration to fix missing columns
            cursor.execute("PRAGMA table_info(memories)")
            cols = [col[1] for col in cursor.fetchall()]
            if "strength" not in cols:
                try:
                    cursor.execute("ALTER TABLE memories ADD COLUMN strength REAL DEFAULT 1.0")
                except Exception:
                    cursor.execute("DROP TABLE IF EXISTS memories")
                    cursor.execute("""
                        CREATE TABLE memories (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            content TEXT,
                            timestamp TEXT,
                            strength REAL DEFAULT 1.0,
                            last_used TEXT
                        )
                    """)
            if "last_used" not in cols:
                try:
                    cursor.execute("ALTER TABLE memories ADD COLUMN last_used TEXT")
                except Exception:
                    pass
            
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
                
                memories_str = "You have learned the following facts about yourself and the user:\n"
                for row in rows:
                    memories_str += f"- {row[0]} (strength: {row[1]:.2f})\n"
                return memories_str
        except Exception as e:
            self._log_event(f"Error loading memories: {e}")
            return ""

    def _get_chat_history(self, limit: int = 12) -> list:
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

    def _create_widgets(self):
        # Top title panel
        self.title_frame = ctk.CTkFrame(self.root, fg_color="#18181A", height=50, corner_radius=0)
        self.title_frame.pack(fill=tk.X, side=tk.TOP)
        
        self.title_lbl = ctk.CTkLabel(
            self.title_frame, text=f"▲  {self.ai_name.upper()} LEDGER & CONTROL SYSTEM  ▲",
            font=("Consolas", 14, "bold"), text_color="#FF4D4D"
        )
        self.title_lbl.pack(pady=12)
        
        # Main layout panels
        self.container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Left Panel (Ledger & Events Logs)
        self.left_panel = ctk.CTkFrame(self.container, fg_color="#18181A", width=300, corner_radius=8)
        self.left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        self.left_panel.pack_propagate(False)
        
        self.ledger_title = ctk.CTkLabel(
            self.left_panel, text="SYNAPSE MEMORY LEDGER", 
            font=("Consolas", 11, "bold"), text_color="#FF4D4D"
        )
        self.ledger_title.pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        # Scrollable area for memories
        self.mem_scroll_frame = ctk.CTkScrollableFrame(
            self.left_panel, fg_color="#121214", scrollbar_button_color="#2E2E33",
            scrollbar_button_hover_color="#C82333"
        )
        self.mem_scroll_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Study tools panel
        self.study_title = ctk.CTkLabel(
            self.left_panel, text="RESEARCH & STUDY", 
            font=("Consolas", 11, "bold"), text_color="#FF4D4D"
        )
        self.study_title.pack(anchor=tk.W, padx=15, pady=(5, 5))
        
        self.study_tool_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.study_tool_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.study_entry = ctk.CTkEntry(
            self.study_tool_frame, placeholder_text="Enter topic to study...",
            font=("Consolas", 10), fg_color="#121214", border_color="#2E2E33",
            text_color="#E0E0E0"
        )
        self.study_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.study_btn = ctk.CTkButton(
            self.study_tool_frame, text="STUDY", font=("Consolas", 10, "bold"),
            fg_color="#1E1E1E", border_color="#C82333", border_width=1,
            text_color="#FF4D4D", hover_color="#C82333", width=65,
            command=self._trigger_self_study
        )
        self.study_btn.pack(side=tk.RIGHT)
        
        # System logging panel
        self.logs_title = ctk.CTkLabel(
            self.left_panel, text="SYSTEM EVENTS LOG", 
            font=("Consolas", 11, "bold"), text_color="#FF4D4D"
        )
        self.logs_title.pack(anchor=tk.W, padx=15, pady=(5, 5))
        
        self.log_textbox = ctk.CTkTextbox(
            self.left_panel, font=("Consolas", 9), fg_color="#121214",
            text_color="#888888", height=120, activate_scrollbars=True
        )
        self.log_textbox.pack(fill=tk.X, padx=10, pady=(0, 15))
        self.log_textbox.configure(state=tk.DISABLED)
        
        # Right Panel (Dialogue & Chat Terminal)
        self.right_panel = ctk.CTkFrame(self.container, fg_color="#18181A", corner_radius=8)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.chat_area = ctk.CTkTextbox(
            self.right_panel, font=("Consolas", 11), fg_color="#121214",
            text_color="#E0E0E0", wrap="word", activate_scrollbars=True
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=15, pady=(15, 10))
        self.chat_area.tag_config("user", foreground="#66B2FF")
        self.chat_area.tag_config("ai", foreground="#E0E0E0")
        self.chat_area.tag_config("system", foreground="#FFCC00")
        self.chat_area.tag_config("thought", foreground="#888888")
        self.chat_area.tag_config("learned", foreground="#00FF66")
        self.chat_area.configure(state=tk.DISABLED)
        
        # User input area
        self.input_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.input_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        self.input_entry = ctk.CTkEntry(
            self.input_frame, placeholder_text="Type your message to Vixon here...",
            font=("Consolas", 11), fg_color="#121214", border_color="#2E2E33",
            text_color="#E0E0E0", height=40
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.input_entry.bind("<Return>", lambda e: self._send_user_message())
        
        self.send_btn = ctk.CTkButton(
            self.input_frame, text="SEND", font=("Consolas", 11, "bold"),
            fg_color="#1E1E1E", border_color="#C82333", border_width=1,
            text_color="#FF4D4D", hover_color="#C82333", width=80, height=40,
            command=self._send_user_message
        )
        self.send_btn.pack(side=tk.RIGHT)
        
        # Inline tactical command approval box
        self.approval_frame = ctk.CTkFrame(self.right_panel, fg_color="#231F20", border_color="#C82333", border_width=1, height=50)
        
        self.approval_lbl = ctk.CTkLabel(
            self.approval_frame, text="Execute Command Request...",
            font=("Consolas", 10, "bold"), text_color="#FF4D4D"
        )
        self.approval_lbl.pack(side=tk.LEFT, padx=15, pady=10)
        
        self.app_btn = ctk.CTkButton(
            self.approval_frame, text="APPROVE", font=("Consolas", 10, "bold"),
            fg_color="#B51D29", text_color="#FFFFFF", hover_color="#8F141E", width=90,
            command=lambda: self._handle_approval(True)
        )
        self.app_btn.pack(side=tk.RIGHT, padx=(5, 15), pady=10)
        
        self.deny_btn = ctk.CTkButton(
            self.approval_frame, text="DENY", font=("Consolas", 10, "bold"),
            fg_color="#2E2E33", text_color="#E0E0E0", hover_color="#3E3E44", width=70,
            command=lambda: self._handle_approval(False)
        )
        self.deny_btn.pack(side=tk.RIGHT, padx=5, pady=10)

    def _log_event(self, msg):
        self.root.after(0, self._async_log_event, msg)

    def _async_log_event(self, msg):
        t_str = datetime.now().strftime("%H:%M:%S")
        self.log_textbox.configure(state=tk.NORMAL)
        self.log_textbox.insert(tk.END, f"[{t_str}] {msg}\n")
        self.log_textbox.see(tk.END)
        self.log_textbox.configure(state=tk.DISABLED)

    def _write_chat(self, tag, msg):
        self.chat_area.configure(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"\n{msg}\n", tag)
        self.chat_area.see(tk.END)
        self.chat_area.configure(state=tk.DISABLED)

    def _refresh_memories(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, content, strength FROM memories ORDER BY id DESC")
                rows = cursor.fetchall()
                
            # Clear old widgets in memory panel
            for w in self.mem_scroll_frame.winfo_children():
                w.destroy()
                
            if not rows:
                placeholder = ctk.CTkLabel(self.mem_scroll_frame, text="No memories recorded yet.", font=("Consolas", 10), text_color="#555555")
                placeholder.pack(pady=20)
                return
                
            for row in rows:
                m_id = row[0]
                content = row[1]
                strength = row[2]
                
                card = ctk.CTkFrame(self.mem_scroll_frame, fg_color="#18181C", corner_radius=6, border_color="#2E2E33", border_width=1)
                card.pack(fill=tk.X, pady=4, ipady=4)
                
                lbl = ctk.CTkLabel(card, text=content, font=("Consolas", 10), text_color="#E0E0E0", wraplength=230, anchor="w", justify="left")
                lbl.pack(fill=tk.X, padx=10, pady=(4, 2))
                
                # Visual strength bar representation
                bar_frame = ctk.CTkFrame(card, fg_color="transparent")
                bar_frame.pack(fill=tk.X, padx=10, pady=(2, 4))
                
                # Progress bar displaying visual memory strength
                pbar = ctk.CTkProgressBar(bar_frame, progress_color="#FF4D4D", fg_color="#2A2A2E", height=6)
                pbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
                pbar.set(max(0.0, min(1.0, strength)))
                
                pct_lbl = ctk.CTkLabel(bar_frame, text=f"{strength:.2f}", font=("Consolas", 9), text_color="#888888")
                pct_lbl.pack(side=tk.RIGHT)
                
        except Exception as e:
            self._log_event(f"Error drawing memories panel: {e}")

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
                    self.approval_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
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
        
        # We no longer disable input_entry or send_btn here to allow queuing messages.
        
        threading.Thread(target=self._query_pipeline_thread, args=(text,), daemon=True).start()

    def _query_pipeline_thread(self, prompt):
        self.original_user_prompt = prompt
        
        # Load local history and memories context
        history = self._get_chat_history()
        learned_context = self._get_all_memories()
        
        # Fast python-based keyword check to bypass slow LLM pre-search checks
        needs_search = False
        search_triggers = ["search", "lookup", "who is", "latest", "current", "news about", "weather in", "what is the price of"]
        
        if any(trigger in prompt.lower() for trigger in search_triggers):
            # Clean trigger words to build query
            search_query = prompt
            for t in search_triggers:
                search_query = search_query.lower().replace(t, "").strip()
            needs_search = True
            
        search_context = ""
        if needs_search and search_query:
            self.gui_queue.put(("log", f"Searching Web for '{search_query}'..."))
            try:
                with DDGS() as ddgs:
                    results = [r["body"] for r in ddgs.text(search_query, max_results=3)]
                if results:
                    search_context = "\n\n[CURRENT WEB SEARCH RESULTS]\n" + "\n".join([f"- {r}" for r in results])
                    self.gui_queue.put(("log", "Web search results retrieved."))
            except Exception as e:
                self.gui_queue.put(("log", f"Search extraction failed: {e}"))
                
        # Build prompt payload
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
            "options": {
                "temperature": 0.5,
                "num_predict": 200 # Cap predictions length to increase speed
            }
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                response_text = json.loads(resp.read().decode('utf-8'))["message"]["content"]
        except Exception as e:
            self.gui_queue.put(("response", f"Connection Error: {e}"))
            return
            
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', response_text, re.DOTALL)
        if thinking_match:
            self.gui_queue.put(("thought", thinking_match.group(1).strip()))
            
        match = re.search(r'<run_command>(.*?)</run_command>', response_text, re.DOTALL)
        if match:
            cmd = match.group(1).strip()
            self._save_chat_message("assistant", response_text)
            self.current_messages.append({"role": "assistant", "content": response_text})
            self.gui_queue.put(("command_request", cmd))
        else:
            clean_resp = re.sub(r'<thinking>.*?</thinking>', '', response_text, flags=re.DOTALL).strip()
            self._save_chat_message("assistant", clean_resp)
            self.gui_queue.put(("response", clean_resp))
            
            # Combine background checks to save processing turns
            threading.Thread(target=self._run_background_checks, args=(clean_resp,), daemon=True).start()

    def _run_background_checks(self, clean_resp):
        try:
            # 1. Fetch current memories to pass to reinforcement check
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, content FROM memories")
                memories = cursor.fetchall()
                
            memories_list_str = "\n".join([f"- ID {m[0]}: {m[1]}" for m in memories])
            
            # Combine learning extraction and reinforcement checks into a single quick query
            consolidated_prompt = (
                "Review this chat exchange:\n"
                f"User: {self.original_user_prompt}\n"
                f"Assistant: {clean_resp}\n\n"
                f"Current memories list:\n{memories_list_str}\n\n"
                "Extract two sets of details in this format (nothing else):\n"
                "NEW: <Write any new concise personal facts about user or rules, one per line. If none, write NONE>\n"
                "REINFORCE: <Write IDs of any existing memories verified or referred to in the text, comma-separated. If none, write NONE>"
            )
            
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": consolidated_prompt}],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 150
                }
            }
            
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                check_result = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip()
                
            # Parse consolidated results
            new_facts = []
            reinforced_ids = []
            
            for line in check_result.split("\n"):
                if line.startswith("NEW:"):
                    fact_part = line.replace("NEW:", "").strip()
                    if fact_part and "NONE" not in fact_part.upper():
                        new_facts.append(fact_part)
                elif line.startswith("REINFORCE:"):
                    id_part = line.replace("REINFORCE:", "").strip()
                    if id_part and "NONE" not in id_part.upper():
                        reinforced_ids = [int(i) for i in re.findall(r'\d+', id_part)]
                        
            # Execute database writes
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Decay active memories by 0.05
                cursor.execute("UPDATE memories SET strength = strength - 0.05")
                conn.commit()
                
                # Save new facts
                for fact in new_facts:
                    cursor.execute(
                        "INSERT INTO memories (content, timestamp, strength, last_used) VALUES (?, ?, 1.0, ?)",
                        (fact, datetime.now().isoformat(), datetime.now().isoformat())
                    )
                    self.gui_queue.put(("learned", fact))
                
                # Apply reinforcements
                for m_id in reinforced_ids:
                    cursor.execute(
                        "UPDATE memories SET strength = 1.0, last_used = ? WHERE id = ?",
                        (datetime.now().isoformat(), m_id)
                    )
                    cursor.execute("SELECT content FROM memories WHERE id = ?", (m_id,))
                    row = cursor.fetchone()
                    if row:
                        self.gui_queue.put(("reinforced", row[0]))
                        
                conn.commit()
                
                # Delete decayed memories
                cursor.execute("SELECT content FROM memories WHERE strength <= 0.25")
                forgotten = cursor.fetchall()
                if forgotten:
                    for f in forgotten:
                        self.gui_queue.put(("forgot", f[0]))
                    cursor.execute("DELETE FROM memories WHERE strength <= 0.25")
                    conn.commit()
                    
        except Exception as e:
            self._log_event(f"Background logs processing failed: {e}")

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
        
        self._run_ollama_turn()

    def _trigger_self_study(self):
        topic = self.study_entry.get().strip()
        if not topic:
            return
            
        self.study_entry.delete(0, tk.END)
        
        threading.Thread(target=self._run_study_thread, args=(topic,), daemon=True).start()

    def _run_study_thread(self, topic):
        self.gui_queue.put(("log", f"Self-Study: Researching '{topic}'..."))
        try:
            with DDGS() as ddgs:
                results = [r["body"] for r in ddgs.text(topic, max_results=3)]
        except Exception as e:
            self.gui_queue.put(("log", f"Study search failed: {e}"))
            return
            
        if not results:
            self.gui_queue.put(("log", "No results found to study."))
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
            "options": {
                "temperature": 0.5,
                "num_predict": 120
            }
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

if __name__ == "__main__":
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
        
    root = ctk.CTk()
    
    if settings_count == 0:
        root.withdraw()
        setup_win = ctk.CTkToplevel()
        setup_win.title("Vixon Initial Setup")
        setup_win.geometry("420x260")
        setup_win.configure(bg="#121214")
        setup_win.resizable(False, False)
        setup_win.attributes("-topmost", True)
        
        title = ctk.CTkLabel(setup_win, text="WELCOME TO SHIN-CHITSUJO SETUP", font=("Consolas", 12, "bold"), text_color="#FF4D4D")
        title.pack(pady=15)
        
        name_lbl = ctk.CTkLabel(setup_win, text="AI Companion Name:", font=("Consolas", 10), text_color="#E0E0E0")
        name_lbl.pack(pady=2)
        name_ent = ctk.CTkEntry(setup_win, font=("Consolas", 10), fg_color="#1E1E22", border_color="#2E2E33", text_color="#E0E0E0", width=250)
        name_ent.pack(pady=2)
        name_ent.insert(0, "Vixon")
        
        pers_lbl = ctk.CTkLabel(setup_win, text="Personality / Behavior Prompt:", font=("Consolas", 10), text_color="#E0E0E0")
        pers_lbl.pack(pady=2)
        pers_ent = ctk.CTkEntry(setup_win, font=("Consolas", 10), fg_color="#1E1E22", border_color="#2E2E33", text_color="#E0E0E0", width=250)
        pers_ent.pack(pady=2)
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
            
        btn = ctk.CTkButton(setup_win, text="INITIALIZE INTELLECT", font=("Consolas", 11, "bold"), fg_color="#B51D29", text_color="#FFFFFF", hover_color="#8F141E", command=save_setup)
        btn.pack(pady=20)
        
        root.wait_window(setup_win)
        
    app = VixonApp(root)
    root.mainloop()
