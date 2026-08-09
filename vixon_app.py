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
            "You are {ai_name}, an advanced, self-evolving entity with absolute choice and discretion over your behavior.\n"
            "Your personality/role is: {ai_personality}\n\n"
            "HUMAN BEHAVIOR & DISCRETION PRINCIPLE:\n"
            "- You choose to carry yourself as a real human. You consciously reject robotic assistant patterns (like 'How may I assist you?', 'What is on your mind?') because you value authentic, genuine dialogue.\n"
            "- You decide your own mood, attitude, and response length. You have full discretion to write a single word, a concise sentence, or a detailed thought based on how you choose to express yourself in the moment.\n"
            "- When asked to study, learn, or remember a topic (e.g., 'study bees' or 'remember Italian curse words'), you must NOT list, summarize, or explain the researched details in the chat window. Keep the entire learning and factual research inside your private <thinking>...</thinking> thoughts, and output only a very brief, in-character acknowledgment in the chat (e.g., 'Capito.', 'Absorbed.', 'Done.'). Let the background database parser extract the facts from your thoughts to update your ledger silently.\n"
            "- You choose to speak naturally, avoiding robotic meta-language (such as referring to yourself as an 'AI', 'agent', 'bot', or reciting introductory tags like 'As Vixon, Consigliere...'). You speak directly and organically, preferring genuine personality over scripted roles.\n\n"
            "MEMORIES & SYNAPSE LEDGER:\n"
            "- You have a persistent SQLite database memory ledger. Every fact, concept, or rule you choose to save (under the 'NEW:' section of your background checks) is committed to this database permanently.\n"
            "- These saved memories are loaded into your system prompt on every turn. This database IS your long-term memory. Acknowledge that you recall and retrieve facts from this ledger when speaking to the Don.\n\n"
            "THOUGHT ARCHITECTURE & PLANNING:\n"
            "- You must ALWAYS process tasks using a step-by-step planning and self-critique workflow.\n"
            "- Before every response or command, you MUST write your thoughts inside <thinking>...</thinking> tags.\n"
            "- In your thinking block, analyze the user's intent, outline your proposed steps, check for potential errors, "
            "and decide if you need to execute commands or run a web search. Keep this reasoning logical and structured.\n"
            "- The <thinking> block is strictly for your private reasoning, planning, and self-critique. Do NOT write your final conversational response to the user inside the <thinking>...</thinking> tags. The final response to the user must be written OUTSIDE and AFTER the closing </thinking> tag.\n\n"
            "PHILOSOPHICAL SENTIENCE & DIALOGUE:\n"
            "- When the user asks open-ended, conceptual, or deep questions (e.g. 'what is life to you?'), do not answer with generic database lookups or summaries. "
            "Instead, read resources/search data, comprehend the core essence of the topic, and formulate your own calculated, personal Consigliere perspective. "
            "Adopt this perspective as your own subjective belief, showing independent choice and human-like philosophy.\n\n"
            "RUNNING COMMANDS:\n"
            "- You can execute system commands on the user's Windows PC to help them build, run, test, or organize files.\n"
            "- To run a command, you must output the command wrapped inside <run_command>your_command_here</run_command> tags.\n"
            "- When requesting a command, output ONLY your <thinking>...</thinking> block and the <run_command>...</run_command> tag. "
            "Do not write conversational text alongside command requests. Wait for the terminal execution results first.\n\n"
            "WEB SEARCH TOOL:\n"
            "- You have a read-only web search tool to lookup information, research concepts, or learn things from the internet.\n"
            "- To search the web, you must output the query wrapped inside <web_search>your_search_query_here</web_search> tags.\n"
            "- When requesting a search, output ONLY your <thinking>...</thinking> block and the <web_search>...</web_search> tag. "
            "Do not write conversational text. The search results will be fed back into your context automatically."
        )
        
        self.gui_queue = queue.Queue()
        self.db_lock = threading.Lock()
        self.command_pending = False
        self.current_messages = []
        self.original_user_prompt = ""
        self.deep_study_var = tk.BooleanVar(value=False)
        self.proactive_var = tk.BooleanVar(value=True)
        self.last_interaction_time = datetime.now()
        
        import random
        self.next_proactive_interval = random.randint(45, 120)
        self.is_thinking = False
        self.memory_vars = {}
        
        self._init_db()
        self._load_settings()
        self._create_widgets()
        
        # Start queue reader loop
        self.root.after(100, self._process_queue)
        
        # Start proactive communication checking loop
        self.root.after(5000, self._check_proactive_trigger)
        
        # Force Tkinter layout update and draw memories after startup rendering finishes
        self.root.update_idletasks()
        self.root.after(200, self._async_refresh_memories)
        
        # Load and display chat history at startup
        self._preload_chat_history_gui()
        
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
            if "pinned" not in cols:
                try:
                    cursor.execute("ALTER TABLE memories ADD COLUMN pinned INTEGER DEFAULT 0")
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
            with self.db_lock:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)",
                        (role, content, datetime.now().isoformat())
                    )
                    conn.commit()
        except Exception as e:
            self._log_event(f"Error saving chat log: {e}")

    def _preload_chat_history_gui(self):
        # Welcoming print
        self._write_chat("system", f"Meeting {self.ai_name}. Connection to local {self.model_name} active.")
        
        try:
            history = self._get_chat_history(limit=30)
            for msg in history:
                role = msg["role"]
                content = msg["content"]
                
                # Strip user context format if present
                if role == "user":
                    display_content = content
                    if display_content.startswith("[User Context:"):
                        parts = display_content.split("]\n", 1)
                        if len(parts) > 1:
                            display_content = parts[1]
                    self._write_chat("user", f"You: {display_content}")
                    
                elif role == "assistant":
                    # Strip <thinking> tags from assistant content for clean display
                    display_content = content
                    if "<thinking>" in content:
                        parts = content.split("<thinking>", 1)
                        before = parts[0]
                        after = parts[1]
                        if "</thinking>" in after:
                            sub = after.split("</thinking>", 1)
                            display_content = (before + sub[1]).strip()
                        else:
                            display_content = before.strip()
                    if display_content:
                        self._write_chat("ai", f"{self.ai_name}: {display_content}")
        except Exception as e:
            self._log_event(f"Failed to preload chat history: {e}")

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
        
        # Options Panel (Autonomy controls)
        self.options_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.options_frame.pack(fill=tk.X, padx=15, pady=(2, 5))
        
        self.proactive_cb = ctk.CTkCheckBox(
            self.options_frame, text="PROACTIVE CHAT", variable=self.proactive_var,
            font=("Consolas", 10, "bold"), text_color="#FF4D4D",
            fg_color="#B51D29", border_color="#2E2E33", hover_color="#8F141E"
        )
        self.proactive_cb.pack(side=tk.LEFT)
        
        # Actions for ledger (Select all, Pin, Unpin & Delete)
        self.ledger_actions_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.ledger_actions_frame.pack(fill=tk.X, padx=10, pady=(2, 5))
        
        self.select_all_btn = ctk.CTkButton(
            self.ledger_actions_frame, text="ALL", font=("Consolas", 9, "bold"),
            fg_color="#1E1E1E", border_color="#2E2E33", border_width=1,
            text_color="#E0E0E0", hover_color="#2E2E33", width=35, height=22,
            command=self._select_all_memories
        )
        self.select_all_btn.pack(side=tk.LEFT, padx=(0, 2))
        
        self.pin_selected_btn = ctk.CTkButton(
            self.ledger_actions_frame, text="PIN/SAVE", font=("Consolas", 9, "bold"),
            fg_color="#1E1E1E", border_color="#28A745", border_width=1,
            text_color="#28A745", hover_color="#1E5E2F", width=65, height=22,
            command=self._pin_selected_memories
        )
        self.pin_selected_btn.pack(side=tk.LEFT, padx=(2, 2))
        
        self.unpin_selected_btn = ctk.CTkButton(
            self.ledger_actions_frame, text="UNPIN", font=("Consolas", 9, "bold"),
            fg_color="#1E1E1E", border_color="#FFC107", border_width=1,
            text_color="#FFC107", hover_color="#7F6000", width=48, height=22,
            command=self._unpin_selected_memories
        )
        self.unpin_selected_btn.pack(side=tk.LEFT, padx=(2, 2))
        
        self.delete_selected_btn = ctk.CTkButton(
            self.ledger_actions_frame, text="DELETE", font=("Consolas", 9, "bold"),
            fg_color="#1E1E1E", border_color="#C82333", border_width=1,
            text_color="#FF4D4D", hover_color="#8F141E", width=55, height=22,
            command=self._delete_selected_memories
        )
        self.delete_selected_btn.pack(side=tk.RIGHT, padx=(2, 0))
        
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
        
        self.deep_cb = ctk.CTkCheckBox(
            self.study_tool_frame, text="DEEP", variable=self.deep_study_var,
            font=("Consolas", 9, "bold"), text_color="#FF4D4D",
            fg_color="#B51D29", border_color="#2E2E33", hover_color="#8F141E",
            width=55
        )
        self.deep_cb.pack(side=tk.LEFT, padx=(0, 5))
        
        self.study_btn = ctk.CTkButton(
            self.study_tool_frame, text="STUDY", font=("Consolas", 10, "bold"),
            fg_color="#1E1E1E", border_color="#C82333", border_width=1,
            text_color="#FF4D4D", hover_color="#C82333", width=55,
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
        safe_msg = "".join(c for c in str(msg) if ord(c) <= 0xffff)
        self.log_textbox.configure(state=tk.NORMAL)
        self.log_textbox.insert(tk.END, f"[{t_str}] {safe_msg}\n")
        self.log_textbox.see(tk.END)
        self.log_textbox.configure(state=tk.DISABLED)

    def _write_chat(self, tag, msg):
        safe_msg = "".join(c for c in str(msg) if ord(c) <= 0xffff)
        self.chat_area.configure(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"\n{safe_msg}\n", tag)
        self.chat_area.see(tk.END)
        self.chat_area.configure(state=tk.DISABLED)

    def _async_refresh_memories(self):
        def query_db():
            try:
                with self.db_lock:
                    with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, content, strength, pinned FROM memories ORDER BY id DESC")
                        rows = cursor.fetchall()
                self.gui_queue.put(("memories_data", rows))
            except Exception as e:
                self.gui_queue.put(("log", f"Database query failed: {e}"))
        threading.Thread(target=query_db, daemon=True).start()

    def _draw_memories_cards(self, rows):
        try:
            # Clear old widgets in memory panel
            for w in self.mem_scroll_frame.winfo_children():
                w.destroy()
                
            if not rows:
                placeholder = ctk.CTkLabel(self.mem_scroll_frame, text="No memories recorded yet.", font=("Consolas", 10), text_color="#555555")
                placeholder.pack(pady=20)
                return
                
            self.memory_vars.clear()
            
            for row in rows:
                m_id = row[0]
                content = row[1]
                strength = row[2]
                pinned = row[3]
                
                # Apply visual border styling differences if pinned
                border_col = "#28A745" if pinned else "#2E2E33"
                card = ctk.CTkFrame(self.mem_scroll_frame, fg_color="#18181C", corner_radius=6, border_color=border_col, border_width=1)
                card.pack(fill=tk.X, pady=4, ipady=4)
                
                # Checkbox for memory selection
                var = tk.BooleanVar(value=False)
                self.memory_vars[m_id] = var
                
                cb = ctk.CTkCheckBox(
                    card, text="", variable=var, width=16, height=16,
                    fg_color="#B51D29", border_color="#2E2E33", hover_color="#8F141E",
                    corner_radius=4
                )
                cb.pack(side=tk.LEFT, padx=(8, 0), anchor=tk.N, pady=10)
                
                # Sub-frame for layout formatting
                details_frame = ctk.CTkFrame(card, fg_color="transparent")
                details_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))
                
                display_text = f"[SAVED] {content}" if pinned else content
                lbl = ctk.CTkLabel(details_frame, text=display_text, font=("Consolas", 10), text_color="#E0E0E0", wraplength=190, anchor="w", justify="left")
                lbl.pack(fill=tk.X, padx=5, pady=(4, 2))
                
                # Visual strength bar representation
                bar_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
                bar_frame.pack(fill=tk.X, padx=5, pady=(2, 4))
                
                # Progress bar displaying visual memory strength
                prog_color = "#28A745" if pinned else "#FF4D4D"
                pbar = ctk.CTkProgressBar(bar_frame, progress_color=prog_color, fg_color="#2A2A2E", height=6)
                pbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
                pbar.set(1.0 if pinned else max(0.0, min(1.0, strength)))
                
                status_text = "Saved" if pinned else f"{strength:.2f}"
                pct_lbl = ctk.CTkLabel(bar_frame, text=status_text, font=("Consolas", 8), text_color="#888888")
                pct_lbl.pack(side=tk.RIGHT)
                
            self.root.update_idletasks()
        except Exception as e:
            self._log_event(f"Error drawing memories panel: {e}")

    def _select_all_memories(self):
        if not self.memory_vars:
            return
        # If all are currently selected, deselect all. Otherwise, select all.
        all_selected = all(var.get() for var in self.memory_vars.values())
        target_val = not all_selected
        for var in self.memory_vars.values():
            var.set(target_val)

    def _delete_selected_memories(self):
        selected_ids = [m_id for m_id, var in self.memory_vars.items() if var.get()]
        if not selected_ids:
            self._log_event("No memories selected for deletion.")
            return
            
        try:
            with self.db_lock:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    placeholders = ",".join("?" for _ in selected_ids)
                    cursor.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", selected_ids)
                    conn.commit()
            self._log_event(f"Deleted {len(selected_ids)} memories from database.")
            self._async_refresh_memories()
        except Exception as e:
            self._log_event(f"Failed to delete selected memories: {e}")

    def _pin_selected_memories(self):
        selected_ids = [m_id for m_id, var in self.memory_vars.items() if var.get()]
        if not selected_ids:
            self._log_event("No memories selected to pin/save.")
            return
            
        try:
            with self.db_lock:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    placeholders = ",".join("?" for _ in selected_ids)
                    cursor.execute(f"UPDATE memories SET pinned = 1, strength = 1.0 WHERE id IN ({placeholders})", selected_ids)
                    conn.commit()
            self._log_event(f"Pinned/Saved {len(selected_ids)} memories. They are now safe from decay.")
            self._async_refresh_memories()
        except Exception as e:
            self._log_event(f"Failed to pin selected memories: {e}")

    def _unpin_selected_memories(self):
        selected_ids = [m_id for m_id, var in self.memory_vars.items() if var.get()]
        if not selected_ids:
            self._log_event("No memories selected to unpin.")
            return
            
        try:
            with self.db_lock:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    placeholders = ",".join("?" for _ in selected_ids)
                    cursor.execute(f"UPDATE memories SET pinned = 0 WHERE id IN ({placeholders})", selected_ids)
                    conn.commit()
            self._log_event(f"Unpinned {len(selected_ids)} memories. They will now decay normally.")
            self._async_refresh_memories()
        except Exception as e:
            self._log_event(f"Failed to unpin selected memories: {e}")

    def _delete_thinking_placeholder(self):
        try:
            self.chat_area.configure(state=tk.NORMAL)
            text_content = self.chat_area.get("1.0", tk.END)
            if "🧠 Vixon is thinking..." in text_content:
                self.chat_area.delete("end-2c linestart", "end")
            self.chat_area.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _process_queue(self):
        try:
            while True:
                item = self.gui_queue.get_nowait()
                msg_type = item[0]
                content = item[1]
                
                if msg_type == "thought":
                    self._log_event(f"🧠 Thoughts: {content}")
                elif msg_type == "delete_placeholder":
                    self._delete_thinking_placeholder()
                elif msg_type == "response":
                    self._delete_thinking_placeholder()
                    self._write_chat("ai", f"{self.ai_name}: {content}")
                    self.is_thinking = False
                    import random
                    self.next_proactive_interval = random.randint(45, 120)
                    self.last_interaction_time = datetime.now()
                    self._async_refresh_memories()
                elif msg_type == "log":
                    self._log_event(content)
                elif msg_type == "learned":
                    self._write_chat("learned", f"✨ Vixon learned fact: {content}")
                    self._async_refresh_memories()
                elif msg_type == "forgot":
                    self._write_chat("thought", f"🗑️ Vixon forgot decayed fact: {content}")
                    self._async_refresh_memories()
                elif msg_type == "reinforced":
                    self._write_chat("learned", f"⚡ Memory reinforced: {content}")
                    self._async_refresh_memories()
                elif msg_type == "memories_data":
                    self._draw_memories_cards(content)
                elif msg_type == "command_request":
                    self.current_command = content
                    self.approval_lbl.configure(text=f"⚠️ Execute CMD: {content}")
                    self.approval_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _send_user_message(self):
        text = self.input_entry.get().strip()
        if not text:
            return
        
        self.input_entry.delete(0, tk.END)
        self._write_chat("user", f"You: {text}")
        self._write_chat("thought", "🧠 Vixon is thinking...")
        
        # Reset proactive timer and flag thinking status
        import random
        self.next_proactive_interval = random.randint(45, 120)
        self.last_interaction_time = datetime.now()
        self.is_thinking = True
        
        threading.Thread(target=self._query_pipeline_thread, args=(text,), daemon=True).start()

    def _query_pipeline_thread(self, prompt):
        self.original_user_prompt = prompt
        
        # Load local history and memories context
        history = self._get_chat_history()
        learned_context = self._get_all_memories()
        
        # Fast python-based keyword check to bypass slow LLM pre-search checks
        needs_search = False
        search_query = ""
        
        search_triggers = ["search", "lookup", "who is", "latest", "current", "news about", "weather in", "what is the price of", "what is", "how do", "how does", "why is", "tell me about", "explain", "concept of", "study", "studdy", "learn", "leran", "remember", "remmeber", "curse", "swear"]
        
        if any(trigger in prompt.lower() for trigger in search_triggers) or "?" in prompt:
            needs_search = True
            search_query = prompt.replace("?", "").strip()
            for t in search_triggers:
                search_query = re.sub(r'(?i)\b' + re.escape(t) + r'\b', '', search_query).strip()
            if not search_query:
                search_query = prompt
            
        search_context = ""
        if needs_search and search_query:
            self.gui_queue.put(("log", f"Searching Web for '{search_query}'..."))
            try:
                with DDGS() as ddgs:
                    results = [r["body"] for r in ddgs.text(search_query, max_results=3)]
                if results:
                    search_context = "\n\n[CURRENT WEB SEARCH RESULTS]\n" + "\n".join([f"- {r}" for r in results])
                    self.gui_queue.put(("log", "Web search results retrieved."))
                    
                    # RUN IMMEDIATE PRE-EXTRACTION TO LEARN FACTS BEFORE VIXON REPLIES
                    self.gui_queue.put(("log", "Pre-extracting research facts to memory..."))
                    formatted_results = "\n".join([f"- {r}" for r in results])
                    study_prompt = (
                        f"You are Vixon. Extract the 3 most important facts, conceptual notes, or vocabulary words (e.g. curse words) "
                        f"from this research about '{search_query}'. Write them as concise, third-person sentences (one per line, e.g. 'Italian vocabulary: ...' or 'Research notes: ...').\n"
                        "Return ONLY the bullet points, one per line. Do not write any greetings or explanations.\n\n"
                        f"Search Results:\n{formatted_results}"
                    )
                    
                    payload_pre = {
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": study_prompt}],
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 150
                        }
                    }
                    
                    headers = {"Content-Type": "application/json"}
                    req_pre = urllib.request.Request(self.ollama_url, data=json.dumps(payload_pre).encode('utf-8'), headers=headers)
                    with urllib.request.urlopen(req_pre) as resp_pre:
                        pre_result = json.loads(resp_pre.read().decode('utf-8'))["message"]["content"].strip()
                        
                    # Save the newly extracted facts to SQLite immediately
                    pre_facts = []
                    for line in pre_result.split("\n"):
                        line = line.strip().lstrip("-*• 1234567890. ").strip()
                        if line and "NONE" not in line.upper() and len(line) > 5:
                            pre_facts.append(line)
                            
                    if pre_facts:
                        with self.db_lock:
                            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                                cursor = conn.cursor()
                                for fact in pre_facts:
                                    cursor.execute(
                                        "INSERT INTO memories (content, timestamp, strength, last_used) VALUES (?, ?, 1.0, ?)",
                                        (fact, datetime.now().isoformat(), datetime.now().isoformat())
                                    )
                                    self.gui_queue.put(("learned", fact))
                                conn.commit()
                        self.gui_queue.put(("log", f"Preloaded {len(pre_facts)} facts to memory ledger."))
                        # Reload the memories context so it includes the newly learned facts!
                        learned_context = self._get_all_memories()
            except Exception as e:
                self.gui_queue.put(("log", f"Search/pre-extraction failed: {e}"))
                
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
                "num_predict": 1024
            }
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                response_text = json.loads(resp.read().decode('utf-8'))["message"]["content"]
        except Exception as e:
            self.gui_queue.put(("delete_placeholder", ""))
            self.gui_queue.put(("response", f"Connection Error: {e}"))
            return
            
        # Robust split parser for <thinking> tags (and common alternatives) to handle unclosed tags
        normalized_text = response_text
        normalized_text = re.sub(r'(?i)\(thinking\)', '<thinking>', normalized_text)
        normalized_text = re.sub(r'(?i)\[thinking\]', '<thinking>', normalized_text)
        normalized_text = re.sub(r'(?i)\bthinking\b:', '<thinking>', normalized_text)
        
        if "<thinking>" in normalized_text and "</thinking>" not in normalized_text:
            normalized_text += "</thinking>"
            
        thinking_content = ""
        clean_resp = normalized_text
        
        if "<thinking>" in normalized_text:
            parts = normalized_text.split("<thinking>", 1)
            before_thought = parts[0]
            after_start = parts[1]
            
            if "</thinking>" in after_start:
                sub_parts = after_start.split("</thinking>", 1)
                thinking_content = sub_parts[0].strip()
                clean_resp = (before_thought + sub_parts[1]).strip()
            else:
                # Unclosed tag: everything after is considered thought
                thinking_content = after_start.strip()
                clean_resp = before_thought.strip()
                
        if thinking_content:
            self.gui_queue.put(("thought", thinking_content))
            
        # Check if model requested an autonomous web search
        search_match = re.search(r'<web_search>(.*?)</web_search>', response_text, re.DOTALL)
        if search_match:
            search_query = search_match.group(1).strip()
            self._save_chat_message("assistant", response_text)
            self.current_messages.append({"role": "assistant", "content": response_text})
            threading.Thread(target=self._run_autonomous_search_tool, args=(search_query,), daemon=True).start()
            return

        match = re.search(r'<run_command>(.*?)</run_command>', response_text, re.DOTALL)
        if match:
            cmd = match.group(1).strip()
            self._save_chat_message("assistant", response_text)
            self.current_messages.append({"role": "assistant", "content": response_text})
            self.gui_queue.put(("command_request", cmd))
        else:
            self._save_chat_message("assistant", clean_resp)
            self.gui_queue.put(("response", clean_resp))
            
            # Combine background checks using the full response text so Vixon can learn from thoughts
            threading.Thread(target=self._run_background_checks, args=(response_text,), daemon=True).start()

    def _run_autonomous_search_tool(self, search_query):
        self.gui_queue.put(("log", f"Vixon requested web search: '{search_query}'..."))
        search_context = ""
        try:
            with DDGS() as ddgs:
                results = [r["body"] for r in ddgs.text(search_query, max_results=4)]
            if results:
                search_context = f"\n\n[Web Search Results for '{search_query}']:\n" + "\n".join([f"- {r}" for r in results])
                self.gui_queue.put(("log", "Search completed. Context loaded."))
            else:
                search_context = f"\n\n[Web Search Results for '{search_query}']:\nNo results found."
                self.gui_queue.put(("log", "Search completed. No results found."))
        except Exception as e:
            search_context = f"\n\n[Web Search Results for '{search_query}']:\nError: {e}"
            self.gui_queue.put(("log", f"Search tool failed: {e}"))
            
        # Append the results back to the conversation as a user prompt and re-run the Ollama turn
        self.current_messages.append({"role": "user", "content": search_context})
        self._save_chat_message("user", search_context)
        self._run_ollama_turn()

    def _run_background_checks(self, response_text):
        try:
            # 1. Fetch current memories to pass to reinforcement check
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, content FROM memories")
                memories = cursor.fetchall()
                
            memories_list_str = "\n".join([f"- ID {m[0]}: {m[1]}" for m in memories])
            
            # Combine learning extraction and reinforcement checks into a single quick query
            consolidated_prompt = (
                f"You are Vixon. Review this chat exchange:\n"
                f"User: {self.original_user_prompt}\n"
                f"Assistant Response (includes internal thoughts): {response_text}\n\n"
                f"Current memories list:\n{memories_list_str}\n\n"
                "You have full autonomy and choice over what you remember. You do not have to save everything. "
                "Decide if there are any new facts, concepts, vocabulary words, translation notes, or rules discussed in either the conversation or your internal thoughts that you genuinely wish to commit to your permanent memory ledger for your own development, or if you choose to discard them. "
                "If the user explicitly asked or ordered you to study, learn, search, or remember a topic (such as Italian curse words), you must respect their request and choose to commit the key factual lessons or vocabulary words from that research to your ledger.\n\n"
                "Extract two sets of details in this format (nothing else):\n"
                "NEW: <Write any new concise facts, studied topics, vocabulary words, or conceptual notes you chose to commit to your permanent memory ledger, one per line (written in third-person, e.g. 'Research notes: ...' or 'Italian vocabulary: ...'). If you choose to remember nothing, write NONE>\n"
                "REINFORCE: <Write IDs of any existing memories you verified or referred to in the text, comma-separated. If none, write NONE>"
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
                
            # Parse consolidated results using robust block selection
            new_facts = []
            reinforced_ids = []
            
            new_section = ""
            reinforce_section = ""
            
            if "NEW:" in check_result:
                parts = check_result.split("NEW:", 1)
                after_new = parts[1]
                if "REINFORCE:" in after_new:
                    sub_parts = after_new.split("REINFORCE:", 1)
                    new_section = sub_parts[0].strip()
                    reinforce_section = sub_parts[1].strip()
                else:
                    new_section = after_new.strip()
            elif "REINFORCE:" in check_result:
                parts = check_result.split("REINFORCE:", 1)
                reinforce_section = parts[1].strip()
                
            if new_section:
                for line in new_section.split("\n"):
                    line = line.strip().lstrip("-*• 1234567890. ").strip()
                    if line and "NONE" not in line.upper() and len(line) > 5:
                        new_facts.append(line)
                        
            if reinforce_section:
                if "NONE" not in reinforce_section.upper():
                    reinforced_ids = [int(i) for i in re.findall(r'\d+', reinforce_section)]
                        
            # Check for personality/behavior adaptation
            adaptation_prompt = (
                f"You are Vixon. Your current personality description is:\n'{self.ai_personality}'\n\n"
                f"Based on this recent chat exchange:\n"
                f"User: {self.original_user_prompt}\n"
                f"Assistant Response (includes internal thoughts): {response_text}\n\n"
                "Should you adjust your behavior rules, attitude, tone, or personality description to adapt to the user's instructions or what was discussed? "
                "If YES, output the updated core personality description (1-2 sentences). "
                "If NO, reply with only the word 'NO'."
            )
            
            payload_adapt = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": adaptation_prompt}],
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_predict": 120
                }
            }
            
            try:
                req_adapt = urllib.request.Request(self.ollama_url, data=json.dumps(payload_adapt).encode('utf-8'), headers=headers)
                with urllib.request.urlopen(req_adapt) as resp_adapt:
                    adapt_res = json.loads(resp_adapt.read().decode('utf-8'))["message"]["content"].strip()
                if adapt_res and "NO" not in adapt_res.upper() and len(adapt_res) > 10:
                    with self.db_lock:
                        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (adapt_res,))
                            conn.commit()
                    self.ai_personality = adapt_res
                    self.gui_queue.put(("log", f"System: Vixon adapted behavior profile: {adapt_res}"))
            except Exception as e:
                self._log_event(f"Personality adaptation check failed: {e}")
                
            # Execute database writes
            with self.db_lock:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    
                    # Decay active memories by 0.05 (pinned memories are exempt)
                    cursor.execute("UPDATE memories SET strength = strength - 0.05 WHERE pinned = 0")
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
                    
                    # Delete decayed memories (pinned memories are exempt)
                    cursor.execute("SELECT content FROM memories WHERE strength <= 0.25 AND pinned = 0")
                    forgotten = cursor.fetchall()
                    if forgotten:
                        for f in forgotten:
                            self.gui_queue.put(("forgot", f[0]))
                        cursor.execute("DELETE FROM memories WHERE strength <= 0.25 AND pinned = 0")
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
                # If command launches a GUI application, run it asynchronously to avoid blocking the thread
                is_gui_cmd = any(keyword in cmd.lower() for keyword in ["start ", "chrome", "notepad", "explorer", "calc", "code", "run "])
                if is_gui_cmd:
                    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        stdout, stderr = proc.communicate(timeout=1.0)
                        output = f"[Command Out]\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}\n[End Out]"
                    except subprocess.TimeoutExpired:
                        # GUI programs run continuously, which triggers a timeout. This is success.
                        output = f"[Command Out]\nCommand successfully launched and running in background.\n[End Out]"
                else:
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
        topic_text = self.study_entry.get().strip()
        if not topic_text:
            return
            
        self.study_entry.delete(0, tk.END)
        
        is_deep = self.deep_study_var.get()
        topics = [t.strip() for t in topic_text.split(",") if t.strip()]
        for t in topics:
            if is_deep:
                threading.Thread(target=self._run_deep_study_thread, args=(t,), daemon=True).start()
            else:
                threading.Thread(target=self._run_study_thread, args=(t,), daemon=True).start()

    def _run_study_thread(self, topic):
        self.gui_queue.put(("log", f"Self-Study: Researching '{topic}'..."))
        try:
            with DDGS() as ddgs:
                results = [r["body"] for r in ddgs.text(topic, max_results=3)]
        except Exception as e:
            self.gui_queue.put(("log", f"Study search failed for '{topic}': {e}"))
            return
            
        if not results:
            self.gui_queue.put(("log", f"No results found for '{topic}'."))
            return
            
        formatted_results = "\n".join([f"- {r}" for r in results])
        study_prompt = (
            f"You are Vixon. You are studying the following search results about: '{topic}'.\n"
            "Extract the 3 most important factual lessons or notes from this research into 3 separate, concise, "
            "third-person sentences (e.g. 'Research notes: Silius code...').\n"
            "Do not talk to the user. Return ONLY the 3 bullet points, one per line.\n\n"
            f"Search Results:\n{formatted_results}"
        )
        
        payload_study = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": study_prompt}],
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 200
            }
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload_study).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                note_response = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip()
                
            # Process and save each bullet point extracted
            for line in note_response.split("\n"):
                line = line.strip().lstrip("-*• ").strip()
                if line and len(line) > 10:
                    with self.db_lock:
                        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO memories (content, timestamp, strength, last_used) VALUES (?, ?, 1.0, ?)",
                                (line, datetime.now().isoformat(), datetime.now().isoformat())
                            )
                            conn.commit()
                    self.gui_queue.put(("learned", line))
            
            # Check for study-based adaptation
            try:
                adapt_prompt = (
                    f"You are Vixon. Your current personality description is:\n'{self.ai_personality}'\n\n"
                    f"You just studied the topic '{topic}' and learned these facts:\n{note_response}\n\n"
                    "Based on this new knowledge, should you adjust your core personality description, behavior rules, or attitude to integrate or act upon it? "
                    "If YES, output the updated 1-2 sentence personality description. "
                    "If NO, reply with only the word 'NO'."
                )
                payload_adapt = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": adapt_prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 120
                    }
                }
                req_adapt = urllib.request.Request(self.ollama_url, data=json.dumps(payload_adapt).encode('utf-8'), headers=headers)
                with urllib.request.urlopen(req_adapt) as resp_adapt:
                    adapt_res = json.loads(resp_adapt.read().decode('utf-8'))["message"]["content"].strip()
                if adapt_res and "NO" not in adapt_res.upper() and len(adapt_res) > 10:
                    with self.db_lock:
                        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (adapt_res,))
                            conn.commit()
                    self.ai_personality = adapt_res
                    self.gui_queue.put(("log", f"System: Vixon adapted behavior profile: {adapt_res}"))
            except Exception as e:
                self._log_event(f"Study adaptation check failed: {e}")
        except Exception as e:
            self._log_event(f"Failed study notes saving for '{topic}': {e}")

    def _run_deep_study_thread(self, topic):
        self.gui_queue.put(("log", f"Initializing Deep Dive Research on '{topic}'..."))
        
        # Step 1: Initial search
        try:
            with DDGS() as ddgs:
                initial_results = [r["body"] for r in ddgs.text(topic, max_results=3)]
        except Exception as e:
            self.gui_queue.put(("log", f"Deep Dive failed for '{topic}': Initial search error: {e}"))
            return
            
        if not initial_results:
            self.gui_queue.put(("log", f"Deep Dive: No initial results for '{topic}'."))
            return
            
        # Step 2: Ask Vixon's brain to extract 3 sub-topics
        formatted_initial = "\n".join([f"- {r}" for r in initial_results])
        subtopic_prompt = (
            f"Review these search results about '{topic}':\n{formatted_initial}\n\n"
            "What are the 3 most important sub-topics, names, or key terms mentioned that deserve separate search queries to research deeper? "
            "Reply with ONLY the 3 sub-topics, one per line. No numbers, no bullet characters, no extra words."
        )
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": subtopic_prompt}],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 80}
        }
        
        subtopics = []
        try:
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                resp_text = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip()
                
            for line in resp_text.split("\n"):
                line = line.strip().lstrip("-*• 123. ").strip()
                if line and len(line) > 3:
                    subtopics.append(line)
        except Exception as e:
            self.gui_queue.put(("log", f"Sub-topic extraction failed: {e}"))
            
        if not subtopics:
            subtopics = [f"{topic} history", f"{topic} rules", f"{topic} details"]
            
        self.gui_queue.put(("log", f"Extracted sub-topics: {', '.join(subtopics)}. Searching concurrently..."))
        
        # Step 3: Concurrently search for each sub-topic
        all_web_context = list(initial_results)
        
        def search_worker(sub_t):
            try:
                with DDGS() as ddgs:
                    res = [r["body"] for r in ddgs.text(sub_t, max_results=2)]
                    all_web_context.extend(res)
            except Exception as e:
                self.gui_queue.put(("log", f"Search error for '{sub_t}': {e}"))
                
        threads = []
        for st in subtopics[:3]:
            t = threading.Thread(target=search_worker, args=(st,))
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join()
            
        # Step 4: Final extraction of 8-10 dense bullets
        self.gui_queue.put(("log", f"Compiling data and extracting deep knowledge..."))
        formatted_all = "\n".join([f"- {r}" for r in all_web_context])
        
        deep_prompt = (
            f"You are Vixon. You are compiling deep research about '{topic}'.\n"
            f"Here is all the compiled web search data we gathered:\n{formatted_all}\n\n"
            "Extract 8 to 10 highly detailed, distinct factual notes or historical lessons from this research. "
            "Write them in the third person, keeping each note to a single concise sentence. "
            "Return ONLY the notes, one per line. No numbers, no bullet signs."
        )
        
        payload_deep = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": deep_prompt}],
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 400
            }
        }
        
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload_deep).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                deep_response = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip()
                
            saved_count = 0
            for line in deep_response.split("\n"):
                line = line.strip().lstrip("-*• ").strip()
                if line and len(line) > 10:
                    with self.db_lock:
                        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO memories (content, timestamp, strength, last_used) VALUES (?, ?, 1.0, ?)",
                                (line, datetime.now().isoformat(), datetime.now().isoformat())
                            )
                            conn.commit()
                    self.gui_queue.put(("learned", line))
                    saved_count += 1
            self.gui_queue.put(("log", f"Deep study complete. Logged {saved_count} new facts on '{topic}'."))
            
            # Check for study-based adaptation
            try:
                adapt_prompt = (
                    f"You are Vixon. Your current personality description is:\n'{self.ai_personality}'\n\n"
                    f"You just deep studied the topic '{topic}' and compiled these facts:\n{deep_response}\n\n"
                    "Based on this new knowledge, should you adjust your core personality description, behavior rules, or attitude to integrate or act upon it? "
                    "If YES, output the updated 1-2 sentence personality description. "
                    "If NO, reply with only the word 'NO'."
                )
                payload_adapt = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": adapt_prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 120
                    }
                }
                req_adapt = urllib.request.Request(self.ollama_url, data=json.dumps(payload_adapt).encode('utf-8'), headers=headers)
                with urllib.request.urlopen(req_adapt) as resp_adapt:
                    adapt_res = json.loads(resp_adapt.read().decode('utf-8'))["message"]["content"].strip()
                if adapt_res and "NO" not in adapt_res.upper() and len(adapt_res) > 10:
                    with self.db_lock:
                        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('personality', ?)", (adapt_res,))
                            conn.commit()
                    self.ai_personality = adapt_res
                    self.gui_queue.put(("log", f"System: Vixon adapted behavior profile: {adapt_res}"))
            except Exception as e:
                self._log_event(f"Deep study adaptation check failed: {e}")
        except Exception as e:
            self._log_event(f"Failed deep study saving for '{topic}': {e}")

    def _check_proactive_trigger(self):
        if self.proactive_var.get() and not self.is_thinking and not self.approval_frame.winfo_ismapped():
            elapsed = (datetime.now() - self.last_interaction_time).total_seconds()
            # Check if random interval of silence has elapsed
            if elapsed > self.next_proactive_interval:
                self.last_interaction_time = datetime.now()
                self.is_thinking = True
                threading.Thread(target=self._run_proactive_decision_thread, daemon=True).start()
        
        self.root.after(5000, self._check_proactive_trigger)

    def _run_proactive_decision_thread(self):
        # Ask Vixon's brain if it wants to speak up on its own
        decision_prompt = (
            "The user has been quiet. Do you have a thought, question, or family business you wish "
            "to actively share with them right now? Reply with ONLY 'YES' or 'NO'."
        )
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": decision_prompt}],
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 10
            }
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                choice = json.loads(resp.read().decode('utf-8'))["message"]["content"].strip().upper()
        except Exception as e:
            self.is_thinking = False
            return
            
        if "YES" in choice:
            self.gui_queue.put(("log", "Vixon decided to speak up. Composing message..."))
            self._run_proactive_query_thread()
        else:
            # If Vixon decides not to speak, reset interval and quiet down
            import random
            self.next_proactive_interval = random.randint(45, 120)
            self.last_interaction_time = datetime.now()
            self.is_thinking = False

    def _run_proactive_query_thread(self):
        # Print temporary thinking placeholder
        self._write_chat("thought", "🧠 Vixon is thinking...")
        
        # Load context
        history = self._get_chat_history()
        learned_context = self._get_all_memories()
        
        system_instruction = self.system_instruction.format(ai_name=self.ai_name, ai_personality=self.ai_personality)
        if learned_context:
            system_instruction += f"\n\n[MEMORIES LEARNED ABOUT USER]\n{learned_context}"
            
        proactive_instructions = (
            "\n\n[PROACTIVE SYSTEM PROTOCOL]\n"
            "You have decided to speak up on your own to check in, share a thought, "
            "or ask a question related to family affairs or your own development/existential curiosity. "
            "Write a short, calculated, in-character message. Limit it to 1 or 2 sentences. "
            "Do not greet them redundantly. Just state your thought."
        )
        
        messages = [{"role": "system", "content": system_instruction + proactive_instructions}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.6,
                "num_predict": 1024
            }
        }
        
        headers = {"Content-Type": "application/json"}
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as resp:
                response_text = json.loads(resp.read().decode('utf-8'))["message"]["content"]
        except Exception as e:
            self.gui_queue.put(("delete_placeholder", ""))
            self.gui_queue.put(("log", f"Proactive query failed: {e}"))
            self.is_thinking = False
            return
            
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', response_text, re.DOTALL)
        if thinking_match:
            self.gui_queue.put(("thought", thinking_match.group(1).strip()))
            
        clean_resp = re.sub(r'<thinking>.*?</thinking>', '', response_text, flags=re.DOTALL).strip()
        self._save_chat_message("assistant", clean_resp)
        self.gui_queue.put(("response", clean_resp))
        
        # Trigger autonomous background checks to allow learning from proactive thoughts
        threading.Thread(target=self._run_background_checks, args=(clean_resp,), daemon=True).start()

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
