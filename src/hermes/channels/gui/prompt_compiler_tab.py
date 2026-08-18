import os
import re
import sys
import requests
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Ensure correct pathing for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.channels.gui.theme import COLORS, font, mono, primary_button_kwargs, secondary_button_kwargs
from hermes.channels.gui.components import LabeledEntry, LabeledTextbox
from hermes.runtime import config
from hermes.application.core.ai_router import get_router

class PromptCompilerTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance
        self.selected_file_path = None
        self.doc_content = ""
        
        # Configure layout
        self.tab.grid_columnconfigure(0, weight=3) # Left Panel (Controls)
        self.tab.grid_columnconfigure(1, weight=7) # Right Panel (Workspace)
        self.tab.grid_rowconfigure(0, weight=1)

        self.setup_left_panel()
        self.setup_right_panel()

    def setup_left_panel(self):
        # Left container
        self.left_frame = ctk.CTkScrollableFrame(self.tab, fg_color="transparent", width=280)
        self.left_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        # Header
        ctk.CTkLabel(
            self.left_frame, 
            text="⚙️ Prompt Compiler", 
            font=font(16, "bold"), 
            text_color=COLORS["accent"]
        ).pack(anchor="w", pady=(5, 2))
        
        ctk.CTkLabel(
            self.left_frame, 
            text="Biến prompt thô thành prompt chất lượng cao\ntuân thủ chuẩn cấu trúc XML/Tags.", 
            font=font(11), 
            text_color=COLORS["muted"],
            justify="left"
        ).pack(anchor="w", pady=(0, 12))

        # OpenRouter API Key override
        self.api_key_entry = LabeledEntry(
            self.left_frame, 
            label_text="OpenRouter API Key (Tùy chọn):",
            placeholder="Mặc định sử dụng key hệ thống..."
        )
        self.api_key_entry.entry.configure(show="*")
        self.api_key_entry.pack(fill="x", pady=6)
        
        # Load existing key as placeholder if present
        existing_or_key = os.environ.get("OPENROUTER_API_KEY", "") or getattr(config, "OPENROUTER_API_KEY", "")
        if existing_or_key:
            self.api_key_entry.entry.configure(placeholder_text="Đã cấu hình key hệ thống (••••••••)")

        # LLM Model Selector
        ctk.CTkLabel(
            self.left_frame, 
            text="Mô hình LLM:", 
            font=font(12, "bold"), 
            text_color=COLORS["muted"],
            anchor="w"
        ).pack(fill="x", pady=(6, 2))
        
        self.model_options = [
            "Free - google/gemini-2.5-flash-lite:free",
            "Free - meta-llama/llama-3.3-70b-instruct:free",
            "Free - google/gemini-2.0-flash-exp:free",
            "Gemini (Native) - gemini-2.5-flash",
            "Groq - llama-3.3-70b-versatile",
            "Ollama (Local) - Llama3.2"
        ]
        self.model_var = ctk.StringVar(value=self.model_options[0])
        self.model_menu = ctk.CTkOptionMenu(
            self.left_frame,
            values=self.model_options,
            variable=self.model_var,
            fg_color=COLORS["surface_2"],
            button_color=COLORS["control"],
            button_hover_color=COLORS["control_hover"],
            dropdown_fg_color=COLORS["surface_2"],
            dropdown_hover_color=COLORS["control_hover"],
            text_color=COLORS["text"],
            font=font(12)
        )
        self.model_menu.pack(fill="x", pady=(0, 6))

        # Output Language Selector
        ctk.CTkLabel(
            self.left_frame, 
            text="Ngôn ngữ đầu ra:", 
            font=font(12, "bold"), 
            text_color=COLORS["muted"],
            anchor="w"
        ).pack(fill="x", pady=(6, 2))
        
        self.lang_options = ["Vietnamese", "English"]
        self.lang_var = ctk.StringVar(value=self.lang_options[0])
        self.lang_menu = ctk.CTkOptionMenu(
            self.left_frame,
            values=self.lang_options,
            variable=self.lang_var,
            fg_color=COLORS["surface_2"],
            button_color=COLORS["control"],
            button_hover_color=COLORS["control_hover"],
            dropdown_fg_color=COLORS["surface_2"],
            dropdown_hover_color=COLORS["control_hover"],
            text_color=COLORS["text"],
            font=font(12)
        )
        self.lang_menu.pack(fill="x", pady=(0, 6))

        # Document Context Upload
        ctk.CTkLabel(
            self.left_frame, 
            text="Tài liệu ngữ cảnh (Tùy chọn):", 
            font=font(12, "bold"), 
            text_color=COLORS["muted"],
            anchor="w"
        ).pack(fill="x", pady=(6, 2))
        
        doc_row = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        doc_row.pack(fill="x", pady=(0, 6))
        
        self.btn_browse = ctk.CTkButton(
            doc_row, 
            text="📁 Chọn tệp", 
            command=self.choose_document,
            width=90,
            height=30,
            **secondary_button_kwargs()
        )
        self.btn_browse.pack(side="left", padx=(0, 5))
        
        self.lbl_file_status = ctk.CTkLabel(
            doc_row,
            text="Chưa chọn tài liệu",
            font=font(11),
            text_color=COLORS["subtle"],
            anchor="w"
        )
        self.lbl_file_status.pack(side="left", fill="x", expand=True)

        # Clear Document Context
        self.btn_clear_doc = ctk.CTkButton(
            self.left_frame,
            text="Xóa tài liệu đính kèm",
            command=self.clear_document,
            height=26,
            fg_color="transparent",
            text_color=COLORS["danger"],
            hover_color=COLORS["danger_bg"],
            font=font(11)
        )
        self.btn_clear_doc.pack(fill="x", pady=4)
        self.btn_clear_doc.pack_forget() # Hide initially

        # Compile Button
        self.btn_compile = ctk.CTkButton(
            self.left_frame, 
            text="⚡ Biên dịch Prompt (Compile)", 
            command=self.start_compilation,
            height=40, 
            **primary_button_kwargs()
        )
        self.btn_compile.pack(fill="x", pady=(15, 6))

    def setup_right_panel(self):
        # Right container
        self.right_frame = ctk.CTkFrame(self.tab, fg_color="transparent")
        self.right_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(0, weight=4) # Raw prompt height ratio
        self.right_frame.grid_rowconfigure(1, weight=6) # Compiled prompt height ratio

        # Top Textbox: Raw Input
        self.txt_raw = LabeledTextbox(
            self.right_frame, 
            label_text="1. Nhập Prompt thô của bạn (Raw / Vague Prompt):"
        )
        self.txt_raw.grid(row=0, column=0, pady=(0, 10), sticky="nsew")
        self.txt_raw.set("Ví dụ: Viết cho tôi một prompt tạo ảnh chú mèo phi hành gia dễ thương vẽ kiểu hoạt hình 3D Pixar.")

        # Bottom Textbox: Compiled Output
        self.txt_compiled = LabeledTextbox(
            self.right_frame, 
            label_text="2. Prompt đã biên dịch chuẩn hóa (Compiled Prompt):"
        )
        self.txt_compiled.grid(row=1, column=0, pady=(0, 5), sticky="nsew")
        self.txt_compiled.textbox.configure(font=mono(12))
        self.txt_compiled.set("Nhập prompt thô bên trên và bấm nút 'Biên dịch Prompt'...")

        # Action Buttons Row
        action_row = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        action_row.grid(row=2, column=0, pady=(5, 0), sticky="ew")

        self.btn_copy = ctk.CTkButton(
            action_row,
            text="📋 Copy vào Clipboard",
            command=self.copy_to_clipboard,
            width=160,
            height=32,
            **secondary_button_kwargs()
        )
        self.btn_copy.pack(side="left", padx=(0, 10))

        self.btn_save = ctk.CTkButton(
            action_row,
            text="💾 Lưu vào Thư viện Prompt",
            command=self.save_to_library,
            width=180,
            height=32,
            fg_color=COLORS["success_bg"],
            hover_color=COLORS["success"],
            text_color=COLORS["text"],
            font=font(12, "bold")
        )
        self.btn_save.pack(side="left")

    def choose_document(self):
        file_path = filedialog.askopenfilename(
            title="Chọn tệp ngữ cảnh",
            filetypes=[
                ("Text files", "*.txt;*.md;*.json;*.csv;*.py;*.js;*.ts;*.html;*.css"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    self.doc_content = f.read()
                self.selected_file_path = file_path
                self.lbl_file_status.configure(
                    text=f"Đã nạp: {os.path.basename(file_path)} ({len(self.doc_content)} ký tự)",
                    text_color=COLORS["success"]
                )
                self.btn_clear_doc.pack(fill="x", pady=4)
            except Exception as e:
                messagebox.showerror("Lỗi đọc file", f"Không thể đọc file: {str(e)}")

    def clear_document(self):
        self.selected_file_path = None
        self.doc_content = ""
        self.lbl_file_status.configure(text="Chưa chọn tài liệu", text_color=COLORS["subtle"])
        self.btn_clear_doc.pack_forget()

    def copy_to_clipboard(self):
        compiled_text = self.txt_compiled.get().strip()
        if compiled_text and not compiled_text.startswith("Nhập prompt thô"):
            self.tab.clipboard_clear()
            self.tab.clipboard_append(compiled_text)
            self.tab.update() # Keep in clipboard
            messagebox.showinfo("Thành công", "Đã copy Prompt đã biên dịch vào Clipboard!")
        else:
            messagebox.showwarning("Cảnh báo", "Không có nội dung để copy.")

    def save_to_library(self):
        compiled_text = self.txt_compiled.get().strip()
        if not compiled_text or compiled_text.startswith("Nhập prompt thô") or compiled_text.startswith("Đang biên dịch"):
            messagebox.showwarning("Cảnh báo", "Không có nội dung prompt để lưu.")
            return

        # Pop up dialog for prompt ID
        dialog = ctk.CTkInputDialog(
            text="Nhập ID viết liền không dấu cho Prompt (ví dụ: cat_astronaut_3d):", 
            title="Lưu vào Thư viện"
        )
        prompt_id = dialog.get_input()
        if not prompt_id:
            return

        # Sanitize prompt ID
        prompt_id = re.sub(r'[^a-zA-Z0-9_]', '', prompt_id).lower()
        if not prompt_id:
            messagebox.showerror("Lỗi", "ID không hợp lệ.")
            return

        # Define file destination
        from hermes.runtime.resources import get_prompts_dir
        lib_dir = str(get_prompts_dir() / "templates")
        os.makedirs(lib_dir, exist_ok=True)
        dest_file = os.path.join(lib_dir, f"{prompt_id}.md")

        # Compose file content in project format
        file_content = f"""---
id: {prompt_id}
name: Prompt Custom {prompt_id}
type: compiled_prompt
description: Được tạo tự động từ Prompt Compiler GUI.
---

{compiled_text}
"""
        try:
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(file_content)
            messagebox.showinfo("Thành công", f"Đã lưu prompt vào thư viện tại:\n{dest_file}")
        except Exception as e:
            messagebox.showerror("Lỗi ghi file", f"Không thể lưu file: {str(e)}")

    def start_compilation(self):
        raw_prompt = self.txt_raw.get().strip()
        if not raw_prompt:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập prompt thô trước khi biên dịch.")
            return

        self.btn_compile.configure(state="disabled", text="⚡ Đang biên dịch...")
        self.txt_compiled.set("Đang biên dịch và tối ưu hóa cấu trúc prompt của bạn, vui lòng đợi...")
        
        # Override OpenRouter API key if user provided one
        user_key = self.api_key_entry.get().strip()
        if user_key:
            os.environ["OPENROUTER_API_KEY"] = user_key
            
        # Execute in thread to keep GUI responsive
        threading.Thread(
            target=self.run_compilation, 
            args=(raw_prompt, self.doc_content, self.model_var.get(), self.lang_var.get()), 
            daemon=True
        ).start()

    def run_compilation(self, raw_prompt, doc_context, selected_model, language):
        system_instruction = (
            "You are an elite Prompt Engineer specializing in creating structured, precise, "
            "and production-ready prompt templates for advanced LLMs (like Claude 3.5 Sonnet, GPT-4o).\n\n"
            "Your task is to take a raw/vague prompt, optional document context, and translate/compile "
            "it into an structured prompt using clear XML/Markdown tags.\n\n"
            "Use the following structure for the compiled prompt:\n"
            "- <system>: Role, persona, style, and tone of the AI.\n"
            "- <instructions>: Step-by-step clear instructions.\n"
            "- <context>: Relevant background or document text if provided.\n"
            "- <variables>: Placeholders in double curly braces (e.g. {{ variable }}) that the user can replace.\n"
            "- <output_format>: Formats (JSON, Markdown, table) required.\n"
            "- <constraints>: Things the AI MUST NOT do.\n\n"
            "Write the final compiled prompt in the selected language: " + language + ".\n"
            "Keep the output extremely clean, directly outputting the prompt itself without introductory or conversational filler."
        )

        prompt_body = f"Here is the Raw Prompt to compile:\n\"\"\"\n{raw_prompt}\n\"\"\"\n"
        if doc_context:
            prompt_body += f"\nHere is the Context Document content:\n\"\"\"\n{doc_context}\n\"\"\"\n"

        try:
            # Map selected model value to provider and call
            model_str = selected_model.lower()
            
            # API Calls
            if "ollama" in model_str:
                # Local Ollama call
                result = self.call_ollama_directly(prompt_body, system_instruction)
            elif "groq" in model_str:
                # Groq call
                result = self.call_groq_directly(prompt_body, system_instruction)
            elif "native" in model_str:
                # Gemini native call
                result = self.call_gemini_directly(prompt_body, system_instruction)
            else:
                # OpenRouter (default & free models)
                result = self.call_openrouter_directly(model_str, prompt_body, system_instruction)
                
            self.app.after(0, lambda res=result: self.compilation_success(res))
            
        except Exception as e:
            err_msg = str(e)
            self.app.after(0, lambda msg=err_msg: self.compilation_error(msg))

    def compilation_success(self, result):
        self.txt_compiled.set(result)
        self.btn_compile.configure(state="normal", text="⚡ Biên dịch Prompt (Compile)")

    def compilation_error(self, err_msg):
        self.txt_compiled.set(f"LỖI BIÊN DỊCH:\n{err_msg}\n\nVui lòng kiểm tra lại khóa API Key của bạn hoặc thử đổi mô hình LLM khác.")
        self.btn_compile.configure(state="normal", text="⚡ Biên dịch Prompt (Compile)")

    # API Request Helper Functions
    def call_openrouter_directly(self, model_str, prompt, system):
        api_key = os.environ.get("OPENROUTER_API_KEY", "") or getattr(config, "OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("Thiếu OpenRouter API Key. Vui lòng nhập vào ô cấu hình bên trái.")

        # Match model ID
        model_id = "meta-llama/llama-3.3-70b-instruct:free"
        if "llama-3.3-70b" in model_str:
            model_id = "meta-llama/llama-3.3-70b-instruct:free"
        elif "gemini-2.0-flash-exp" in model_str:
            model_id = "google/gemini-2.0-flash-exp:free"
        elif "gemini-2.5-flash-lite" in model_str:
            model_id = "google/gemini-2.5-flash-lite:free"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hermes-video-factory",
            "X-Title": "Hermes Video Factory"
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def call_gemini_directly(self, prompt, system):
        api_key = os.environ.get("GEMINI_API_KEY", "") or getattr(config, "GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("Thiếu Gemini API Key trong cấu hình hệ thống (.env).")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        parts = [{"text": f"[System]: {system}\n\n[User]: {prompt}"}]
        payload = {"contents": [{"parts": parts}]}
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    def call_groq_directly(self, prompt, system):
        api_key = os.environ.get("GROQ_API_KEY", "") or getattr(config, "GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("Thiếu Groq API Key trong cấu hình hệ thống (.env).")
            
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def call_ollama_directly(self, prompt, system):
        ollama_url = getattr(config, "OLLAMA_API_URL", "http://localhost:11434")
        payload = {
            "model": "llama3.2:3b",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.3}
        }
        resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
