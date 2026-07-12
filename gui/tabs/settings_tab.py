import os
import sys
import customtkinter as ctk

# Ensure correct pathing for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import config as _cfg
from gui.theme import COLORS, font, primary_button_kwargs, secondary_button_kwargs
from gui.components import CollapsibleSection, StatusIndicator
from gui.prompt_compiler_tab import PromptCompilerTab

class SettingsTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance
        
        self.tab.grid_columnconfigure(0, weight=1)
        self.tab.grid_rowconfigure(0, weight=1)

        # Use a scrollable frame so both sections fit nicely
        scroll = ctk.CTkScrollableFrame(self.tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        scroll.grid_columnconfigure(0, weight=1)

        # --- Section 1: Biên dịch Prompt Compiler ---
        sec_prompt = CollapsibleSection(scroll, title="Biên Dịch & Biên Soạn Prompt", icon="⚙️",
            subtitle="Tạo và tinh chỉnh prompt AI cho hệ thống Hermes",
            expanded=True, accent_color="#8b5cf6")
        sec_prompt.pack(fill="x", pady=(0, 10))

        self.app._prompt_compiler_frame = ctk.CTkFrame(sec_prompt.body, fg_color="transparent")
        self.app._prompt_compiler_frame.pack(fill="both", expand=True)
        self.app._prompt_compiler_instance = PromptCompilerTab(
            self.app._prompt_compiler_frame,
            self.app
        )

        # --- Section 2: Cấu hình hệ thống ---
        sec_cfg = CollapsibleSection(scroll, title="Cấu Hình Hệ Thống", icon="🔧",
            subtitle="API keys, đường dẫn ffmpeg, thư mục dự án",
            expanded=True, accent_color="#f59e0b")
        sec_cfg.pack(fill="x", pady=(0, 10))

        # Re-build original settings widgets into section body
        self._build_settings_widgets(sec_cfg.body)

    def _build_settings_widgets(self, parent):
        """Build the settings form into a given parent frame, using correct widget names for save_settings()."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=0)

        def row_label(text, r):
            ctk.CTkLabel(parent, text=text, font=font(12, "bold"), anchor="w"
                         ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 2))

        # Gemini API Key
        row_label("🔑 Gemini API Key:", 0)
        self.app.sett_gemini_key = ctk.CTkEntry(parent, placeholder_text="Nhập Gemini API Key...",
                                             height=34, show="•", corner_radius=8,
                                             fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                             text_color=COLORS["text"])
        self.app.sett_gemini_key.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        if getattr(_cfg, "GEMINI_API_KEY", "") and _cfg.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            self.app.sett_gemini_key.insert(0, _cfg.GEMINI_API_KEY)

        # Pexels API Key
        row_label("🖼️ Pexels API Key:", 2)
        self.app.sett_pexels_key = ctk.CTkEntry(parent, placeholder_text="Nhập Pexels API Key...",
                                             height=32, show="•", corner_radius=8,
                                             fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                             text_color=COLORS["text"])
        self.app.sett_pexels_key.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        if getattr(_cfg, "PEXELS_API_KEY", ""):
            self.app.sett_pexels_key.insert(0, _cfg.PEXELS_API_KEY)

        # Pixabay API Key
        row_label("🎨 Pixabay API Key:", 4)
        self.app.sett_pixabay_key = ctk.CTkEntry(parent, placeholder_text="Nhập Pixabay API Key...",
                                              height=32, show="•", corner_radius=8,
                                              fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                              text_color=COLORS["text"])
        self.app.sett_pixabay_key.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        if getattr(_cfg, "PIXABAY_API_KEY", ""):
            self.app.sett_pixabay_key.insert(0, _cfg.PIXABAY_API_KEY)

        # FFmpeg path
        row_label("🎬 Đường dẫn FFmpeg:", 6)
        row_ff = ctk.CTkFrame(parent, fg_color="transparent")
        row_ff.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        row_ff.grid_columnconfigure(0, weight=1)
        self.app.sett_ffmpeg_path = ctk.CTkEntry(row_ff, placeholder_text="Đường dẫn tới ffmpeg.exe...",
                                              height=32, corner_radius=8,
                                              fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                              text_color=COLORS["text"])
        self.app.sett_ffmpeg_path.grid(row=0, column=0, sticky="ew")
        if getattr(_cfg, "FFMPEG_PATH", ""):
            self.app.sett_ffmpeg_path.insert(0, _cfg.FFMPEG_PATH)
        ctk.CTkButton(row_ff, text="...", width=36, height=32,
                      command=self._browse_ffmpeg, **secondary_button_kwargs()
                      ).grid(row=0, column=1, padx=(6, 0))

        # Projects root
        row_label("📁 Thư mục gốc Dự án:", 8)
        row_pr = ctk.CTkFrame(parent, fg_color="transparent")
        row_pr.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        row_pr.grid_columnconfigure(0, weight=1)
        self.app.sett_projects_root = ctk.CTkEntry(row_pr, placeholder_text="Đường dẫn thư mục gốc dự án...",
                                                height=32, corner_radius=8,
                                                fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                                text_color=COLORS["text"])
        self.app.sett_projects_root.grid(row=0, column=0, sticky="ew")
        if getattr(_cfg, "PROJECTS_ROOT", ""):
            self.app.sett_projects_root.insert(0, _cfg.PROJECTS_ROOT)
        ctk.CTkButton(row_pr, text="...", width=36, height=32,
                      command=self._browse_projects_root, **secondary_button_kwargs()
                      ).grid(row=0, column=1, padx=(6, 0))

        # Build all the other keys referenced in save_settings() as hidden entries on self.app
        # GROK_API_KEY
        self.app.sett_grok_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        self.app.sett_grok_key.grid(row=10, column=0, sticky="ew")
        if getattr(_cfg, "GROK_API_KEY", ""):
            self.app.sett_grok_key.insert(0, _cfg.GROK_API_KEY)

        # RUNWAY_API_KEY
        self.app.sett_runway_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "RUNWAY_API_KEY", ""):
            self.app.sett_runway_key.insert(0, _cfg.RUNWAY_API_KEY)

        # PIKA_API_KEY
        self.app.sett_pika_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "PIKA_API_KEY", ""):
            self.app.sett_pika_key.insert(0, _cfg.PIKA_API_KEY)

        # KREA_API_KEY
        self.app.sett_krea_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "KREA_API_KEY", ""):
            self.app.sett_krea_key.insert(0, _cfg.KREA_API_KEY)

        # LEONARDO_API_KEY
        self.app.sett_leonardo_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "LEONARDO_API_KEY", ""):
            self.app.sett_leonardo_key.insert(0, _cfg.LEONARDO_API_KEY)

        # AI_VIDEO_CUSTOM_API_KEY
        self.app.sett_ai_custom_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "AI_VIDEO_CUSTOM_API_KEY", ""):
            self.app.sett_ai_custom_key.insert(0, _cfg.AI_VIDEO_CUSTOM_API_KEY)

        # AI_VIDEO_CUSTOM_ENDPOINT
        self.app.sett_ai_custom_endpoint = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "AI_VIDEO_CUSTOM_ENDPOINT", ""):
            self.app.sett_ai_custom_endpoint.insert(0, _cfg.AI_VIDEO_CUSTOM_ENDPOINT)

        # GROQ_API_KEY
        self.app.sett_groq_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "GROQ_API_KEY", ""):
            self.app.sett_groq_key.insert(0, _cfg.GROQ_API_KEY)

        # CEREBRAS_API_KEY
        self.app.sett_cerebras_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "CEREBRAS_API_KEY", ""):
            self.app.sett_cerebras_key.insert(0, _cfg.CEREBRAS_API_KEY)

        # MISTRAL_API_KEY
        self.app.sett_mistral_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "MISTRAL_API_KEY", ""):
            self.app.sett_mistral_key.insert(0, _cfg.MISTRAL_API_KEY)

        # OPENROUTER_API_KEY
        self.app.sett_openrouter_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "OPENROUTER_API_KEY", ""):
            self.app.sett_openrouter_key.insert(0, _cfg.OPENROUTER_API_KEY)

        # TOGETHER_API_KEY
        self.app.sett_together_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "TOGETHER_API_KEY", ""):
            self.app.sett_together_key.insert(0, _cfg.TOGETHER_API_KEY)

        # ELEVENLABS_API_KEY
        self.app.sett_elevenlabs_key = ctk.CTkEntry(parent, height=0, fg_color="transparent", border_width=0)
        if getattr(_cfg, "ELEVENLABS_API_KEY", ""):
            self.app.sett_elevenlabs_key.insert(0, _cfg.ELEVENLABS_API_KEY)

        # Save button
        ctk.CTkButton(parent, text="💾 Lưu Cấu Hình", command=self.app.save_settings,
                      height=38, **primary_button_kwargs()
                      ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=16)

        # System check section
        ctk.CTkLabel(parent, text="🔍 Kiểm Tra Hệ Thống:", font=font(13, "bold"), anchor="w"
                     ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(4, 6))

        self.app.ffmpeg_ind = StatusIndicator(parent, "FFmpeg")
        self.app.ffmpeg_ind.grid(row=13, column=0, columnspan=2, sticky="w", pady=3)
        self.app.gemini_ind = StatusIndicator(parent, "Gemini AI API")
        self.app.gemini_ind.grid(row=14, column=0, columnspan=2, sticky="w", pady=3)
        self.app.ytdlp_ind = StatusIndicator(parent, "yt-dlp")
        self.app.ytdlp_ind.grid(row=15, column=0, columnspan=2, sticky="w", pady=3)

        row_btns = ctk.CTkFrame(parent, fg_color="transparent")
        row_btns.grid(row=16, column=0, columnspan=2, sticky="ew", pady=10)
        ctk.CTkButton(row_btns, text="▶ FFmpeg", command=self.app.check_ffmpeg, height=28, **secondary_button_kwargs()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_btns, text="▶ Gemini", command=self.app.check_gemini, height=28, **secondary_button_kwargs()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_btns, text="▶ yt-dlp", command=self.app.check_ytdlp, height=28, **secondary_button_kwargs()).pack(side="left")

    def _browse_ffmpeg(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(title="Chọn ffmpeg.exe", filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if path and hasattr(self.app, "sett_ffmpeg_path"):
            self.app.sett_ffmpeg_path.delete(0, "end")
            self.app.sett_ffmpeg_path.insert(0, path)

    def _browse_projects_root(self):
        from tkinter.filedialog import askdirectory
        path = askdirectory(title="Chọn thư mục gốc dự án")
        if path and hasattr(self.app, "sett_projects_root"):
            self.app.sett_projects_root.delete(0, "end")
            self.app.sett_projects_root.insert(0, path)
