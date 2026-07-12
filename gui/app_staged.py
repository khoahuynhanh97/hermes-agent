import os
import sys
import threading
import json
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Add root folder to python path to import core files
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from core.project_manager import ProjectManager
from core.agent_jobs import AgentJobManager, DEFAULT_TASKS
from core.keyword_generator import generate_keywords, translate_to_zh
from core.script_generator import generate_script, save_script_files, SCRIPT_STYLES
from core.file_manager import list_downloaded_materials
from providers.url_list_provider import download_url_list
from providers.pexels_provider import search_and_download_pexels
from providers.pixabay_provider import search_and_download_pixabay
from providers.supplier_feed_provider import run_supplier_feed_provider
from providers.custom_scraper_adapter import run_custom_scraper
from providers.ai_video_provider import AI_VIDEO_PROVIDER_CHOICES, generate_ai_video_materials
from providers.social_search_provider import search_and_download_social
from providers.shopee_search_provider import search_and_download_shopee
from providers.product_image_provider import search_and_download_product_images
from providers.smart_crawler_provider import (
    parse_shopee_url,
    fetch_shopee_product_details,
    search_duckduckgo_urls,
    download_video_clean,
    apply_quality_filter,
    split_audio_video
)
from core.keyword_generator import (
    nlp_expand_keywords,
    extract_keywords_from_product_page
)
import cv2
from PIL import Image, ImageTk
from editor.audio_helper import get_audio_duration
from editor.video_editor import build_tiktok_video
from editor.clip_cutter import cut_single_clip
from gui.components import ConsoleView, LabeledEntry, LabeledTextbox, StatusIndicator, CollapsibleSection, SectionHeader
from gui.theme import COLORS, apply_theme, font, primary_button_kwargs, secondary_button_kwargs
from core.idea_engine import generate_ideas, save_ideas, load_ideas, save_selected_angles, load_selected_angles
from core.prompt_engine import generate_prompts_from_storyboard
from core.clip_library import ClipLibrary, CLIP_STATUSES, ASSET_TYPES, SCENE_TYPES
from core.learning_review import LearningReviewStore
import core.knowledge_base as kb
import core.project_creator as pc
from gui.tabs.settings_tab import SettingsTab
from gui.tabs.learn_review_tab import LearnReviewTab

class HermesTikTokVideoFactoryApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Settings
        self.title("Hermes TikTok Video Factory ≡ƒÄ¼")
        self.geometry("1480x880")
        self.minsize(1200, 760)
        
        # Dark Theme settings
        apply_theme(self)
        
        # State managers
        self.project_manager = ProjectManager()
        self.agent_job_manager = AgentJobManager(self.project_manager)
        self.learning_review_store = LearningReviewStore()
        self.active_project_slug = None
        self.active_project_meta = None
        self.supplier_feed_file = ""
        
        # Manual cutter state
        self.manual_video_path = None
        self.manual_cap = None
        self.manual_duration = 0.0
        self.manual_width = 0
        self.manual_height = 0
        self.manual_fps = 0.0

        # Idea Engine state
        self.idea_checkboxes = []       # list of (idea_dict, BooleanVar)
        self.current_ideas_data = None  # latest ideas dict from AI
        self.clip_library = None        # ClipLibrary instance for active project
        self.lib_clip_cards = []        # list of card frames for library UI refresh

        # Storyboard state
        self.latest_storyboard_data = None
        self.latest_extracted_prompt_data = None
        
        # Handle close protocol to release cv2 resources
        self.protocol("WM_DELETE_WINDOW", self.on_app_closing)
        
        # Build layout
        self.grid_columnconfigure(0, weight=0, minsize=240) # Sidebar
        self.grid_columnconfigure(1, weight=1) # Workspace
        self.grid_rowconfigure(0, weight=1)
        
        self.create_sidebar()
        self.create_workspace()
        self.load_project_list()

    def create_sidebar(self):
        """Creates the sidebar with status indicators and Auto option."""
        self.sidebar = ctk.CTkFrame(self, corner_radius=14, fg_color=COLORS["surface"], border_width=1, border_color=COLORS["border_soft"])
        self.sidebar.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        
        # Logo
        self.logo = ctk.CTkLabel(
            self.sidebar, 
            text="HERMES", 
            font=font(24, "bold"),
            text_color=COLORS["text"]
        )
        self.logo.pack(anchor="w", pady=(24, 2), padx=22)
        self.logo_rule = ctk.CTkFrame(self.sidebar, height=3, width=64, fg_color=COLORS["accent"], corner_radius=999)
        self.logo_rule.pack(anchor="w", padx=22, pady=(0, 10))
        
        self.tagline = ctk.CTkLabel(
            self.sidebar, 
            text="Manifest-driven TikTok studio", 
            font=font(11),
            text_color=COLORS["muted"]
        )
        self.tagline.pack(anchor="w", padx=22, pady=(0, 16))
        
        self.btn_auto_pipeline = ctk.CTkButton(
            self.sidebar,
            text="≡ƒÜÇ Quy Tr├¼nh Tß╗▒ ─Éß╗Öng (Auto)",
            command=self.open_auto_pipeline_dialog,
            height=36,
            fg_color=COLORS["success"],
            hover_color="#16a34a",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_auto_pipeline.pack(fill="x", padx=20, pady=(10, 10))
        
        # Divider
        self.divider = ctk.CTkFrame(self.sidebar, height=2, fg_color="#2d2d34")
        self.divider.pack(fill="x", padx=20, pady=10)
        
        # System checks section
        self.check_label = ctk.CTkLabel(
            self.sidebar, 
            text="Kiß╗âm Tra Hß╗ç Thß╗æng:", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.check_label.pack(anchor="w", padx=20, pady=(5, 5))
        
        # Indicators
        self.ffmpeg_ind = StatusIndicator(self.sidebar, "1. Bß╗Ö giß║úi m├ú FFmpeg")
        self.ffmpeg_ind.pack(fill="x", padx=20, pady=4)
        
        self.gemini_ind = StatusIndicator(self.sidebar, "2. Gemini AI API")
        self.gemini_ind.pack(fill="x", padx=20, pady=4)
        
        self.ytdlp_ind = StatusIndicator(self.sidebar, "3. Th╞░ viß╗çn yt-dlp")
        self.ytdlp_ind.pack(fill="x", padx=20, pady=(4, 12))
        
        # Single compact check button
        self.btn_check_all = ctk.CTkButton(
            self.sidebar, 
            text="≡ƒöº Kiß╗âm Tra Hß╗ç Thß╗æng", 
            command=self._run_all_checks, 
            height=30, 
            **secondary_button_kwargs()
        )
        self.btn_check_all.pack(fill="x", padx=20, pady=(0, 20))
        
        # Keep individual methods as stubs for backward compat
        self.btn_check_ffmpeg = self.btn_check_all
        self.btn_check_gemini = self.btn_check_all
        self.btn_check_ytdlp = self.btn_check_all
        
        self.quick_project_name = None  # Mocked
        
        # Trigger default checks
        self.after(500, self.check_ffmpeg)
        self.after(600, self.check_ytdlp)
        self.after(700, self.check_gemini_silent)

    def create_workspace(self):
        """Creates the tabbed workbook workspace area with topbar project selection."""
        self.workspace_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace_frame.grid(row=0, column=1, padx=(0, 15), pady=15, sticky="nsew")
        self.workspace_frame.grid_rowconfigure(1, weight=1)
        self.workspace_frame.grid_columnconfigure(0, weight=1)
        
        # Flow Switcher Frame / Topbar
        self.flow_switcher_frame = ctk.CTkFrame(self.workspace_frame, fg_color="transparent", height=45)
        self.flow_switcher_frame.grid(row=0, column=0, padx=0, pady=(0, 10), sticky="ew")
        
        # Left container for flows
        flows_container = ctk.CTkFrame(self.flow_switcher_frame, fg_color="transparent")
        flows_container.pack(side="left", fill="y")
        
        self.btn_flow1 = ctk.CTkButton(
            flows_container, 
            text="≡ƒÄ¼ Cß║»t Gh├⌐p Video", 
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            width=180,
            corner_radius=8,
            command=lambda: self.switch_flow(1)
        )
        self.btn_flow1.pack(side="left", padx=(0, 8))

        self.btn_flow2 = ctk.CTkButton(
            flows_container, 
            text="≡ƒºá AI Ph├ón T├¡ch & S├íng Tß║ío", 
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            width=190,
            corner_radius=8,
            command=lambda: self.switch_flow(2)
        )
        self.btn_flow2.pack(side="left", padx=0)
        
        # Right container for project selection
        proj_container = ctk.CTkFrame(self.flow_switcher_frame, fg_color="transparent")
        proj_container.pack(side="right", fill="y", padx=(10, 0))
        
        lbl_proj = ctk.CTkLabel(proj_container, text="≡ƒôü Dß╗▒ ├ín:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_proj.pack(side="left", padx=(0, 6))
        
        self.proj_combobox = ctk.CTkComboBox(
            proj_container,
            values=["Ch╞░a c├│ dß╗▒ ├ín"],
            command=self.on_project_combobox_change,
            height=32,
            width=240
        )
        self.proj_combobox.pack(side="left", padx=(0, 6))
        
        self.btn_new_project = ctk.CTkButton(
            proj_container,
            text="+ Tß║ío Dß╗▒ ├ün",
            height=32,
            width=90,
            command=self.create_quick_project,
            **primary_button_kwargs()
        )
        self.btn_new_project.pack(side="left")

        # Tab Views for Flow 1 and Flow 2
        self.tab_flow1 = ctk.CTkTabview(self.workspace_frame, corner_radius=12, fg_color=COLORS["surface"])
        self.tab_flow2 = ctk.CTkTabview(self.workspace_frame, corner_radius=12, fg_color=COLORS["surface"])
        
        # Tabs for Flow 1 (≡ƒÄ¼ Cß║»t Gh├⌐p Video)
        self.tab_flow1.add("≡ƒôï Sß║ún phß║⌐m")
        self.tab_flow1.add("≡ƒöì T├¼m nguy├¬n liß╗çu")
        self.tab_flow1.add("Γ£é∩╕Å Cß║»t clip")
        self.tab_flow1.add("≡ƒÄ₧∩╕Å Cß║»t thß╗º c├┤ng")
        self.tab_flow1.add("≡ƒôª Kho clip")
        self.tab_flow1.add("≡ƒÄ¼ Dß╗▒ng video")
        self.tab_flow1.add("Γ£à Kß║┐t quß║ú")
        
        # Tabs for Flow 2 (≡ƒºá AI Ph├ón T├¡ch & S├íng Tß║ío)
        self.tab_flow2.add("≡ƒôÜ Hß╗ìc & Duyß╗çt")
        self.tab_flow2.add("≡ƒÆí ├¥ T╞░ß╗ƒng")
        self.tab_flow2.add("≡ƒô¥ Kß╗ïch Bß║ún")
        self.tab_flow2.add("≡ƒÄÖ∩╕Å Giß╗ìng ─Éß╗ìc")
        self.tab_flow2.add("≡ƒû╝∩╕Å Storyboard")
        self.tab_flow2.add("ΓÜÖ∩╕Å C├┤ng Viß╗çc AI")
        self.tab_flow2.add("≡ƒ¢á∩╕Å C├ái ─Éß║╖t")

        # Build tabs
        self.build_tab_product()
        self.build_tab_materials()
        self.build_tab_clip_cutting()
        self.build_tab_manual_cutting()
        self.build_tab_clip_library()
        self.build_tab_editor()
        self.build_tab_results()
        
        self.build_tab_learn_and_review()   # merged: Tr├¡ Thß╗⌐c AI + Duyß╗çt hß╗ìc hß╗Åi
        self.build_tab_idea_engine()
        self.build_tab_script()
        self.build_tab_audio()
        self.build_tab_storyboard()
        self.build_tab_agent_jobs()
        self.build_tab_settings_merged()    # merged: Bi├¬n dß╗ïch Prompt + Cß║Ñu h├¼nh
        
        # Initialize default flow
        self.switch_flow(1)

    def switch_flow(self, flow_id):
        self.current_flow = flow_id
        sec_kwargs = secondary_button_kwargs()
        sec_kwargs["text_color"] = "#a1a1aa"
        if flow_id == 1:
            # Show flow 1, hide flow 2
            self.tab_flow2.grid_remove()
            self.tab_flow1.grid(row=1, column=0, sticky="nsew")
            # Update buttons style
            self.btn_flow1.configure(fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white")
            self.btn_flow2.configure(**sec_kwargs)
        else:
            # Show flow 2, hide flow 1
            self.tab_flow1.grid_remove()
            self.tab_flow2.grid(row=1, column=0, sticky="nsew")
            # Update buttons style
            self.btn_flow1.configure(**sec_kwargs)
            self.btn_flow2.configure(fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white")

    # --- BUILD TABS ---
    
    def build_tab_product(self):
        tab = self.tab_flow1.tab("≡ƒôï Sß║ún phß║⌐m")
        tab.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(tab, text="Th├┤ng Tin Sß║ún Phß║⌐m ─Éang ─É├ính Gi├í", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(15, 10))
        
        # Inputs
        self.in_prod_name = LabeledEntry(tab, "T├¬n dß╗▒ ├ín / sß║ún phß║⌐m *", "V├¡ dß╗Ñ: Gi├í ─æß╗í ─æiß╗çn thoß║íi xoay 360 ─æß╗Ö")
        self.in_prod_name.pack(fill="x", padx=20, pady=5)
        
        self.in_prod_desc = LabeledTextbox(tab, "M├┤ tß║ú sß║ún phß║⌐m ngß║»n gß╗ìn", height=70)
        self.in_prod_desc.pack(fill="x", padx=20, pady=5)
        
        # Price and USP (selling points) in 1 row
        row1 = ctk.CTkFrame(tab, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=5)
        row1.grid_columnconfigure(0, weight=1)
        row1.grid_columnconfigure(1, weight=2)
        
        self.in_prod_price = LabeledEntry(row1, "Gi├í b├ín sß║ún phß║⌐m", "V├¡ dß╗Ñ: 350.000 VN─É")
        self.in_prod_price.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.in_prod_usp = LabeledEntry(row1, "─Éiß╗âm b├ín h├áng cß╗æt l├╡i (USP)", "V├¡ dß╗Ñ: ├üp lß╗▒c n╞░ß╗¢c 1400 lß║ºn/ph├║t, 4 chß║┐ ─æß╗Ö rung")
        self.in_prod_usp.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # Audience and Pain Points in 1 row
        row2 = ctk.CTkFrame(tab, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=5)
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)
        
        self.in_prod_audience = LabeledEntry(row2, "─Éß╗æi t╞░ß╗úng mß╗Ñc ti├¬u", "V├¡ dß╗Ñ: Niß╗üng r─âng, d├ón v─ân ph├▓ng, hß╗ìc sinh")
        self.in_prod_audience.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.in_prod_pain = LabeledEntry(row2, "Nß╗ùi ─æau / Vß║Ñn ─æß╗ü cß╗ºa hß╗ì (Pain Points)", "V├¡ dß╗Ñ: Thß╗⌐c ─ân giß║»t kß║╜ r─âng kh├│ lß║Ñy, s├óu r─âng do chß║úi r─âng kh├┤ng sß║ích")
        self.in_prod_pain.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # Buttons
        self.btn_save_project = ctk.CTkButton(
            tab, 
            text="Khß╗ƒi Tß║ío / L╞░u Dß╗▒ ├ün", 
            command=self.save_project, 
            height=40, 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_save_project.pack(fill="x", padx=20, pady=25)

    def build_tab_materials(self):
        tab = self.tab_flow1.tab("≡ƒöì T├¼m nguy├¬n liß╗çu")
        
        # Left Panel (options) and Right Panel (logs)
        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)
        
        opt_frame = ctk.CTkFrame(tab, fg_color="transparent")
        opt_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        log_frame = ctk.CTkFrame(tab, fg_color="transparent")
        log_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # Mode Selection Tabview
        self.material_tabs = ctk.CTkTabview(opt_frame, height=270)
        self.material_tabs.pack(fill="x", pady=(0, 10))
        
        tab_h1 = self.material_tabs.add("H╞░ß╗¢ng 1: T├¬n sß║ún phß║⌐m")
        tab_h2 = self.material_tabs.add("H╞░ß╗¢ng 2: URL sß║ún phß║⌐m")
        tab_other = self.material_tabs.add("Cß║Ñu h├¼nh kh├íc")
        
        # --- H╞░ß╗¢ng 1 Layout ---
        self.in_h1_query = ctk.CTkEntry(tab_h1, placeholder_text="Nhß║¡p t├¬n sß║ún phß║⌐m (v├¡ dß╗Ñ: Gi├í ─æß╗í ─æiß╗çn thoß║íi xoay 360 ─æß╗Ö)", height=32)
        self.in_h1_query.pack(fill="x", pady=(5, 4))
        
        kw_lbl = ctk.CTkLabel(tab_h1, text="Tß╗½ kh├│a t├¼m kiß║┐m (Search terms):", font=ctk.CTkFont(size=11, weight="bold"))
        kw_lbl.pack(anchor="w", pady=(0, 2))
        
        self.in_keywords_display = ctk.CTkTextbox(tab_h1, height=75)
        self.in_keywords_display.pack(fill="x", pady=(0, 4))
        
        row_keyword_actions = ctk.CTkFrame(tab_h1, fg_color="transparent")
        row_keyword_actions.pack(fill="x", pady=(0, 4))
        row_keyword_actions.grid_columnconfigure(0, weight=1)
        row_keyword_actions.grid_columnconfigure(1, weight=1)

        self.btn_gen_kw = ctk.CTkButton(
            row_keyword_actions,
            text="AI mß╗ƒ rß╗Öng key",
            command=self.generate_project_keywords,
            fg_color="#3b82f6",
            hover_color="#2563eb",
            height=28
        )
        self.btn_gen_kw.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        
        self.btn_run_translate_zh = ctk.CTkButton(
            row_keyword_actions, 
            text="Dß╗ïch key", 
            command=self.run_manual_translation_zh, 
            fg_color="#8b5cf6", 
            hover_color="#7c3aed",
            height=28
        )
        self.btn_run_translate_zh.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        
        self.in_translate_zh_result = LabeledEntry(tab_h1, "Kß║┐t quß║ú dß╗ïch key tiß║┐ng Trung:", "Kß║┐t quß║ú dß╗ïch sß║╜ xuß║Ñt hiß╗çn ß╗ƒ ─æ├óy...")
        self.in_translate_zh_result.pack(fill="x", pady=(2, 2))
        
        # --- H╞░ß╗¢ng 2 Layout ---
        self.in_h2_url = ctk.CTkEntry(tab_h2, placeholder_text="D├ín URL sß║ún phß║⌐m Shopee ß╗ƒ ─æ├óy...", height=32)
        self.in_h2_url.pack(fill="x", pady=(15, 6))
        
        lbl_h2_desc = ctk.CTkLabel(tab_h2, text="≡ƒÆí Hß╗ç thß╗æng sß║╜ tß╗▒ ─æß╗Öng qu├⌐t th├┤ng tin tß╗½ trang Shopee,\nTß║úi lu├┤n video gß╗æc cß╗ºa gian h├áng v├á d├╣ng AI tr├¡ch xuß║Ñt tß╗½ kh├│a\ncß╗æt l├╡i ─æß╗â tiß║┐p tß╗Ñc l├╣ng sß╗Ñc ph├┤i review tr├¬n MXH.", font=ctk.CTkFont(size=11), text_color="#aaaaaa", justify="left")
        lbl_h2_desc.pack(anchor="w", pady=5)
        
        # --- Cß║Ñu h├¼nh kh├íc Layout ---
        # 1. URL Paste
        self.prov_urls_var = ctk.StringVar(value="off")
        self.cb_urls = ctk.CTkCheckBox(tab_other, text="Tß║úi tß╗½ danh s├ích URL tß╗▒ d├ín", variable=self.prov_urls_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_urls.pack(anchor="w", pady=(2, 2))
        
        self.in_urls_paste = ctk.CTkTextbox(tab_other, height=45)
        self.in_urls_paste.pack(fill="x", pady=(0, 4))
        
        # 2. Supplier Feed
        self.prov_feed_var = ctk.StringVar(value="off")
        self.cb_feed = ctk.CTkCheckBox(tab_other, text="Tß║úi tß╗½ Supplier Feed (CSV/JSON)", variable=self.prov_feed_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_feed.pack(anchor="w", pady=1)
        
        row_feed = ctk.CTkFrame(tab_other, fg_color="transparent")
        row_feed.pack(fill="x", pady=(0, 4))
        self.btn_select_feed = ctk.CTkButton(row_feed, text="Chß╗ìn Feed", command=self.select_feed_file, width=80, height=22, font=ctk.CTkFont(size=10))
        self.btn_select_feed.pack(side="left")
        self.lbl_feed_status = ctk.CTkLabel(row_feed, text="Ch╞░a chß╗ìn", font=ctk.CTkFont(size=10), text_color="#888888")
        self.lbl_feed_status.pack(side="left", padx=5)
        
        # 3. AI Video
        self.prov_ai_video_var = ctk.StringVar(value="off")
        self.cb_ai_video = ctk.CTkCheckBox(tab_other, text="Sinh ph├┤i bß║▒ng AI Video (Runway/Pika)", variable=self.prov_ai_video_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_ai_video.pack(anchor="w", pady=1)
        
        ai_video_row = ctk.CTkFrame(tab_other, fg_color="transparent")
        ai_video_row.pack(fill="x", pady=(0, 4))
        self.ai_video_provider_combo = ctk.CTkComboBox(ai_video_row, values=AI_VIDEO_PROVIDER_CHOICES, state="readonly", height=22, width=100, font=ctk.CTkFont(size=10))
        self.ai_video_provider_combo.pack(side="left", padx=(0, 2))
        self.ai_video_provider_combo.set("Grok Imagine")
        
        self.ai_video_prompt_count = ctk.CTkEntry(ai_video_row, placeholder_text="Prompts", height=22, width=45, font=ctk.CTkFont(size=10))
        self.ai_video_prompt_count.pack(side="left", padx=2)
        self.ai_video_prompt_count.insert(0, "3")
        
        self.ai_video_clips_per_prompt = ctk.CTkEntry(ai_video_row, placeholder_text="Clips", height=22, width=35, font=ctk.CTkFont(size=10))
        self.ai_video_clips_per_prompt.pack(side="left", padx=2)
        self.ai_video_clips_per_prompt.insert(0, "1")
        
        self.ai_video_duration = ctk.CTkEntry(ai_video_row, placeholder_text="Gi├óy", height=22, width=35, font=ctk.CTkFont(size=10))
        self.ai_video_duration.pack(side="left", padx=(2, 0))
        self.ai_video_duration.insert(0, "5")
        
        # 4. Cookies Option
        row_cookie = ctk.CTkFrame(tab_other, fg_color="transparent")
        row_cookie.pack(fill="x", pady=(2, 2))
        cookie_lbl = ctk.CTkLabel(row_cookie, text="Cookie tr├¼nh duyß╗çt:", font=ctk.CTkFont(size=10))
        cookie_lbl.pack(side="left", padx=(0, 5))
        self.browser_cookies_combo = ctk.CTkComboBox(row_cookie, values=["Kh├┤ng d├╣ng cookie", "chrome", "edge", "firefox", "brave", "safari"], state="readonly", height=22, width=120, font=ctk.CTkFont(size=10))
        self.browser_cookies_combo.pack(side="left")
        self.browser_cookies_combo.set("Kh├┤ng d├╣ng cookie")
        
        # --- Providers Option frame (Common bottom area) ---
        prov_lbl = ctk.CTkLabel(opt_frame, text="Chß╗ìn nguß╗ôn khai th├íc t├ái nguy├¬n ph├┤i:", font=ctk.CTkFont(size=11, weight="bold"))
        prov_lbl.pack(anchor="w", pady=(2, 2))
        
        self.prov_prod_images_var = ctk.StringVar(value="on")
        self.cb_prod_images = ctk.CTkCheckBox(opt_frame, text="≡ƒô╕ Tß║úi ß║ónh Sß║ún Phß║⌐m HD (Shopee Gallery & Google)", variable=self.prov_prod_images_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_prod_images.pack(anchor="w", pady=1)

        self.prov_social_var = ctk.StringVar(value="on")
        self.cb_social = ctk.CTkCheckBox(opt_frame, text="≡ƒÄ¼ Video Review Thß╗▒c Tß║┐ (TikTok / Bilibili / Shorts)", variable=self.prov_social_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_social.pack(anchor="w", pady=1)

        self.prov_shopee_var = ctk.StringVar(value="on")
        self.cb_shopee = ctk.CTkCheckBox(opt_frame, text="≡ƒ¢ì∩╕Å Video M├┤ Tß║ú Shopee (Gian h├áng ch├¡nh h├úng)", variable=self.prov_shopee_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_shopee.pack(anchor="w", pady=1)

        self.prov_pexels_var = ctk.StringVar(value="off")
        self.cb_pexels = ctk.CTkCheckBox(opt_frame, text="T├¼m tß║úi Pexels Video (Stock chung)", variable=self.prov_pexels_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_pexels.pack(anchor="w", pady=1)
        
        self.prov_pixabay_var = ctk.StringVar(value="off")
        self.cb_pixabay = ctk.CTkCheckBox(opt_frame, text="T├¼m tß║úi Pixabay Video (Stock chung)", variable=self.prov_pixabay_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_pixabay.pack(anchor="w", pady=1)
        
        # Advanced Processing & Quality Gates
        adv_lbl = ctk.CTkLabel(opt_frame, text="Xß╗¡ l├╜ n├óng cao & Cß╗òng chß║Ñt l╞░ß╗úng (Quality Gate):", font=ctk.CTkFont(size=11, weight="bold"))
        adv_lbl.pack(anchor="w", pady=(6, 2))
        
        self.cb_filter_quality_var = ctk.StringVar(value="on")
        self.cb_filter_quality = ctk.CTkCheckBox(opt_frame, text="≡ƒöì Bß╗Ö lß╗ìc chß║Ñt l╞░ß╗úng ph├┤i tß║úi vß╗ü (Local OpenCV)", variable=self.cb_filter_quality_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_filter_quality.pack(anchor="w", pady=1)
        
        self.cb_split_av_var = ctk.StringVar(value="off")
        self.cb_split_av = ctk.CTkCheckBox(opt_frame, text="Γ£é∩╕Å Tß╗▒ ─æß╗Öng t├ích ├óm thanh & h├¼nh ß║únh ph├┤i MXH", variable=self.cb_split_av_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_split_av.pack(anchor="w", pady=1)
        
        # Run Button
        self.btn_run_downloaders = ctk.CTkButton(opt_frame, text="Bß║»t ─Éß║ºu Tß║úi Ph├┤i", command=self.start_downloading_materials, height=35, fg_color="#10b981", hover_color="#059669")
        self.btn_run_downloaders.pack(fill="x", pady=(10, 5))
        
        # Right Console / Log view
        log_lbl = ctk.CTkLabel(log_frame, text="Nhß║¡t k├╜ tß║úi ph├┤i:", font=ctk.CTkFont(size=12, weight="bold"))
        log_lbl.pack(anchor="w", pady=4)
        
        self.downloads_console = ConsoleView(log_frame)
        self.downloads_console.pack(fill="both", expand=True)
        
        self.lbl_downloaded_count = ctk.CTkLabel(log_frame, text="Sß╗æ ph├┤i ─æ├ú tß║úi th├ánh c├┤ng: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10b981")
        self.lbl_downloaded_count.pack(anchor="w", pady=(8, 0))

    def build_tab_clip_cutting(self):
        tab = self.tab_flow1.tab("Γ£é∩╕Å Cß║»t clip")
        
        # Left Panel (options) and Right Panel (logs & stats)
        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)
        
        opt_frame = ctk.CTkFrame(tab, fg_color="transparent")
        opt_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        right_frame = ctk.CTkFrame(tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # Section 1: Cß║Ñu h├¼nh cß║»t
        lbl_sec1 = ctk.CTkLabel(opt_frame, text="1. Cß║Ñu H├¼nh Cß║»t Clip Ph├┤i:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_sec1.pack(anchor="w", pady=(5, 5))
        
        # Inputs in a row
        row_inputs1 = ctk.CTkFrame(opt_frame, fg_color="transparent")
        row_inputs1.pack(fill="x", pady=2)
        row_inputs1.grid_columnconfigure(0, weight=1)
        row_inputs1.grid_columnconfigure(1, weight=1)
        
        self.in_clip_duration = LabeledEntry(row_inputs1, "─Éß╗Ö d├ái mß╗ùi clip (gi├óy)", "2.0")
        self.in_clip_duration.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.in_clip_duration.set("2.0")
        
        self.in_skip_start = LabeledEntry(row_inputs1, "Bß╗Å qua ─æß║ºu video (gi├óy)", "1.0")
        self.in_skip_start.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.in_skip_start.set("1.0")
        
        self.in_max_clips = LabeledEntry(opt_frame, "Sß╗æ clip tß╗æi ─æa tß╗½ mß╗ùi ph├┤i video", "8")
        self.in_max_clips.pack(fill="x", pady=4)
        self.in_max_clips.set("8")
        
        self.cb_vertical_crop_var = ctk.StringVar(value="on")
        self.cb_vertical_crop = ctk.CTkCheckBox(opt_frame, text="Tß╗▒ ─æß╗Öng crop dß╗ìc 9:16 (720x1280)", variable=self.cb_vertical_crop_var, onvalue="on", offvalue="off")
        self.cb_vertical_crop.pack(anchor="w", pady=4)
        
        self.cb_mute_clip_var = ctk.StringVar(value="on")
        self.cb_mute_clip = ctk.CTkCheckBox(opt_frame, text="Tß║»t ├óm thanh clip ph├┤i (Mute)", variable=self.cb_mute_clip_var, onvalue="on", offvalue="off")
        self.cb_mute_clip.pack(anchor="w", pady=4)
        
        # Section 2: Ph├ón t├¡ch chß║Ñt l╞░ß╗úng
        lbl_sec2 = ctk.CTkLabel(opt_frame, text="2. Ph├ón T├¡ch Chß║Ñt L╞░ß╗úng (OpenCV):", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_sec2.pack(anchor="w", pady=(15, 5))
        
        self.cb_quality_analysis_var = ctk.StringVar(value="on")
        self.cb_quality_analysis = ctk.CTkCheckBox(opt_frame, text="Bß║¡t ph├ón t├¡ch ─æß╗Ö s├íng, n├⌐t, chuyß╗ân ─æß╗Öng...", variable=self.cb_quality_analysis_var, onvalue="on", offvalue="off")
        self.cb_quality_analysis.pack(anchor="w", pady=4)
        
        self.cb_discard_bad_clips_var = ctk.StringVar(value="off")
        self.cb_discard_bad_clips = ctk.CTkCheckBox(opt_frame, text="Bß╗Å clip k├⌐m chß║Ñt l╞░ß╗úng (loß║íi Reject)", variable=self.cb_discard_bad_clips_var, onvalue="on", offvalue="off")
        self.cb_discard_bad_clips.pack(anchor="w", pady=4)
        
        # Action Buttons
        self.btn_run_clipper = ctk.CTkButton(opt_frame, text="Bß║»t ─Éß║ºu Cß║»t Clip Ph├┤i", command=self.start_clip_cutting, height=35, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_run_clipper.pack(fill="x", pady=(20, 5))
        
        self.btn_open_clips_dir = ctk.CTkButton(opt_frame, text="Mß╗ƒ Th╞░ Mß╗Ñc Clips", command=self.open_clips_dir, height=35, **secondary_button_kwargs())
        self.btn_open_clips_dir.pack(fill="x", pady=5)
        
        # Right Panel: Results & Console
        stats_frame = ctk.CTkFrame(right_frame, fg_color="#121214", corner_radius=8)
        stats_frame.pack(fill="x", pady=(0, 10))
        
        lbl_stats_title = ctk.CTkLabel(stats_frame, text="B├ío c├ío kß║┐t quß║ú ph├ón t├¡ch:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_stats_title.pack(anchor="w", padx=15, pady=(8, 4))
        
        row_stats = ctk.CTkFrame(stats_frame, fg_color="transparent")
        row_stats.pack(fill="x", padx=15, pady=(0, 8))
        row_stats.grid_columnconfigure(0, weight=1)
        row_stats.grid_columnconfigure(1, weight=1)
        row_stats.grid_columnconfigure(2, weight=1)
        
        self.lbl_total_clips = ctk.CTkLabel(row_stats, text="Tß╗òng clip ─æ├ú tß║ío: 0", font=ctk.CTkFont(size=11, weight="bold"), anchor="w")
        self.lbl_total_clips.grid(row=0, column=0, pady=2, sticky="w")
        
        self.lbl_good_clips = ctk.CTkLabel(row_stats, text="Clip tß╗æt (>=70): 0", font=ctk.CTkFont(size=11), text_color="#22c55e", anchor="w")
        self.lbl_good_clips.grid(row=0, column=1, pady=2, sticky="w")
        
        self.lbl_okay_clips = ctk.CTkLabel(row_stats, text="Clip tß║ím ß╗òn (>=45): 0", font=ctk.CTkFont(size=11), text_color="#3b82f6", anchor="w")
        self.lbl_okay_clips.grid(row=0, column=2, pady=2, sticky="w")
        
        self.lbl_rejected_clips = ctk.CTkLabel(row_stats, text="Clip bß╗ï loß║íi (<45): 0", font=ctk.CTkFont(size=11), text_color="#ef4444", anchor="w")
        self.lbl_rejected_clips.grid(row=1, column=0, pady=2, sticky="w")
        
        self.lbl_failed_clips = ctk.CTkLabel(row_stats, text="Clip lß╗ùi: 0", font=ctk.CTkFont(size=11), text_color="#e2e8f0", anchor="w")
        self.lbl_failed_clips.grid(row=1, column=1, pady=2, sticky="w")
        
        # Console Log
        lbl_log = ctk.CTkLabel(right_frame, text="Nhß║¡t k├╜ cß║»t & ph├ón t├¡ch chß║Ñt l╞░ß╗úng:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_log.pack(anchor="w", pady=(5, 4))
        
        self.clip_cutting_console = ConsoleView(right_frame)
        self.clip_cutting_console.pack(fill="both", expand=True)

        self.clip_cutting_console = ConsoleView(right_frame)
        self.clip_cutting_console.pack(fill="both", expand=True)

    def build_tab_manual_cutting(self):
        tab = self.tab_flow1.tab("≡ƒÄ₧∩╕Å Cß║»t thß╗º c├┤ng")
        
        # Configure layout (Left preview, Right controls)
        tab.grid_columnconfigure(0, weight=5) # Left
        tab.grid_columnconfigure(1, weight=5) # Right
        tab.grid_rowconfigure(0, weight=1)
        
        # Left Panel: Video Frame Preview
        preview_frame = ctk.CTkFrame(tab, fg_color="#121214", corner_radius=12)
        preview_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)
        
        self.manual_preview_label = ctk.CTkLabel(preview_frame, text="Ch╞░a nß║íp video.\nVui l├▓ng nhß║Ñn 'Chß╗ìn Video Ph├┤i' ß╗ƒ cß╗Öt b├¬n phß║úi.", text_color="#71717a")
        self.manual_preview_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Right Panel: Sliders & Settings
        control_frame = ctk.CTkFrame(tab, fg_color="transparent")
        control_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # 1. Video Selection Row
        row_sel = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_sel.pack(fill="x", pady=(5, 5))
        
        btn_select = ctk.CTkButton(row_sel, text="Chß╗ìn Video Ph├┤i", command=self.manual_select_video, **secondary_button_kwargs(), width=120)
        btn_select.pack(side="left", padx=(0, 10))
        
        self.lbl_manual_video_name = ctk.CTkLabel(row_sel, text="Ch╞░a chß╗ìn video ph├┤i", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa", anchor="w")
        self.lbl_manual_video_name.pack(side="left", fill="x", expand=True)
        
        # 2. Metadata Display
        self.lbl_manual_video_meta = ctk.CTkLabel(control_frame, text="Thß╗¥i l╞░ß╗úng: --s | K├¡ch th╞░ß╗¢c: --x-- | FPS: --", font=ctk.CTkFont(size=11), text_color="#71717a", anchor="w")
        self.lbl_manual_video_meta.pack(fill="x", pady=(0, 15))
        
        # 3. Sliders & Time Inputs
        # Start Time
        lbl_start = ctk.CTkLabel(control_frame, text="─Éiß╗âm ─æß║ºu (Start Time):", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_start.pack(fill="x", pady=(5, 2))
        
        row_start = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_start.pack(fill="x", pady=(0, 10))
        row_start.grid_columnconfigure(0, weight=1)
        
        self.slider_manual_start = ctk.CTkSlider(row_start, from_=0.0, to=100.0, command=self.on_manual_start_slider_move, height=16)
        self.slider_manual_start.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.slider_manual_start.set(0.0)
        
        btn_start_dec = ctk.CTkButton(row_start, text="-0.1s", width=40, height=26, fg_color="#27272a", hover_color="#3f3f46", command=lambda: self.adjust_manual_time("start", -0.1))
        btn_start_dec.grid(row=0, column=1, padx=2)
        
        btn_start_inc = ctk.CTkButton(row_start, text="+0.1s", width=40, height=26, fg_color="#27272a", hover_color="#3f3f46", command=lambda: self.adjust_manual_time("start", 0.1))
        btn_start_inc.grid(row=0, column=2, padx=2)
        
        self.in_manual_start = ctk.CTkEntry(row_start, width=55, height=26)
        self.in_manual_start.grid(row=0, column=3, padx=(6, 0))
        self.in_manual_start.insert(0, "0.00")
        self.in_manual_start.bind("<Return>", lambda e: self.on_manual_entry_update("start"))
        
        # End Time
        lbl_end = ctk.CTkLabel(control_frame, text="─Éiß╗âm cuß╗æi (End Time):", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_end.pack(fill="x", pady=(5, 2))
        
        row_end = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_end.pack(fill="x", pady=(0, 15))
        row_end.grid_columnconfigure(0, weight=1)
        
        self.slider_manual_end = ctk.CTkSlider(row_end, from_=0.0, to=100.0, command=self.on_manual_end_slider_move, height=16)
        self.slider_manual_end.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.slider_manual_end.set(10.0)
        
        btn_end_dec = ctk.CTkButton(row_end, text="-0.1s", width=40, height=26, fg_color="#27272a", hover_color="#3f3f46", command=lambda: self.adjust_manual_time("end", -0.1))
        btn_end_dec.grid(row=0, column=1, padx=2)
        
        btn_end_inc = ctk.CTkButton(row_end, text="+0.1s", width=40, height=26, fg_color="#27272a", hover_color="#3f3f46", command=lambda: self.adjust_manual_time("end", 0.1))
        btn_end_inc.grid(row=0, column=2, padx=2)
        
        self.in_manual_end = ctk.CTkEntry(row_end, width=55, height=26)
        self.in_manual_end.grid(row=0, column=3, padx=(6, 0))
        self.in_manual_end.insert(0, "10.00")
        self.in_manual_end.bind("<Return>", lambda e: self.on_manual_entry_update("end"))
        
        # 4. Trimmed Duration
        self.lbl_manual_duration = ctk.CTkLabel(control_frame, text="─Éß╗Ö d├ái ─æoß║ín cß║»t: 0.00s", font=ctk.CTkFont(size=13, weight="bold"), text_color="#60a5fa", anchor="w")
        self.lbl_manual_duration.pack(fill="x", pady=(0, 10))
        
        # 5. Options Checkbox
        row_opts = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_opts.pack(fill="x", pady=(0, 15))
        
        self.cb_manual_vertical_var = ctk.StringVar(value="on")
        self.cb_manual_vertical = ctk.CTkCheckBox(row_opts, text="Tß╗▒ ─æß╗Öng crop dß╗ìc 9:16", variable=self.cb_manual_vertical_var, onvalue="on", offvalue="off")
        self.cb_manual_vertical.pack(side="left", padx=(0, 15))
        
        self.cb_manual_mute_var = ctk.StringVar(value="on")
        self.cb_manual_mute = ctk.CTkCheckBox(row_opts, text="Tß║»t ├óm thanh (Mute)", variable=self.cb_manual_mute_var, onvalue="on", offvalue="off")
        self.cb_manual_mute.pack(side="left")
        
        # 5.5. Save Directory Input
        lbl_save_dir = ctk.CTkLabel(control_frame, text="Th╞░ mß╗Ñc l╞░u clip cß║»t:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_save_dir.pack(fill="x", pady=(5, 2))
        
        row_save_dir = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_save_dir.pack(fill="x", pady=(0, 15))
        
        self.in_manual_save_dir = ctk.CTkEntry(row_save_dir, placeholder_text="─É╞░ß╗¥ng dß║½n th╞░ mß╗Ñc l╞░u clips...")
        self.in_manual_save_dir.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        btn_browse_save_dir = ctk.CTkButton(row_save_dir, text="Chß╗ìn th╞░ mß╗Ñc", width=100, height=28, **secondary_button_kwargs(), command=self.manual_browse_save_dir)
        btn_browse_save_dir.pack(side="left")
        
        # 6. Action Button
        self.btn_manual_cut = ctk.CTkButton(control_frame, text="Bß║»t ─Éß║ºu Cß║»t & L╞░u Clip", command=self.start_manual_cut, height=38, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], state="disabled")
        self.btn_manual_cut.pack(fill="x", pady=(0, 10))
        
        # 7. Progress Bar
        self.manual_progress_bar = ctk.CTkProgressBar(control_frame, progress_color="#3b82f6", fg_color="#27272a")
        self.manual_progress_bar.pack(fill="x", pady=(0, 10))
        self.manual_progress_bar.set(0.0)
        
        # 8. Console Log View
        lbl_console = ctk.CTkLabel(control_frame, text="Nhß║¡t k├╜ tiß║┐n tr├¼nh cß║»t:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_console.pack(fill="x", pady=(5, 2))
        
        self.manual_console = ConsoleView(control_frame, height=130)
        self.manual_console.pack(fill="both", expand=True)

    def manual_select_video(self):
        init_dir = os.path.abspath(os.path.join(os.getcwd(), "projects"))
        if self.active_project_slug:
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            if os.path.exists(folders["materials"]):
                init_dir = folders["materials"]
                
        file_path = filedialog.askopenfilename(
            initialdir=init_dir,
            title="Chß╗ìn Video Ph├┤i",
            filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
            
        self.manual_video_path = file_path
        self.lbl_manual_video_name.configure(text=os.path.basename(file_path))
        
        # Open CV2 VideoCapture
        if self.manual_cap:
            self.manual_cap.release()
            
        self.manual_cap = cv2.VideoCapture(file_path)
        if not self.manual_cap.isOpened():
            messagebox.showerror("Lß╗ùi", "Kh├┤ng thß╗â mß╗ƒ video n├áy.")
            self.manual_video_path = None
            return
            
        self.manual_fps = self.manual_cap.get(cv2.CAP_PROP_FPS)
        total_frames = self.manual_cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self.manual_width = int(self.manual_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.manual_height = int(self.manual_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.manual_duration = total_frames / self.manual_fps if self.manual_fps > 0 else 0.0
        
        # Handle zero division safety
        if self.manual_duration <= 0.0:
            self.manual_duration = 1.0
            
        # Update meta text
        self.lbl_manual_video_meta.configure(
            text=f"Thß╗¥i l╞░ß╗úng: {self.manual_duration:.2f}s | K├¡ch th╞░ß╗¢c: {self.manual_width}x{self.manual_height} | FPS: {self.manual_fps:.1f}"
        )
        
        # Configure sliders
        self.slider_manual_start.configure(from_=0.0, to=self.manual_duration)
        self.slider_manual_end.configure(from_=0.0, to=self.manual_duration)
        
        self.slider_manual_start.set(0.0)
        self.slider_manual_end.set(min(self.manual_duration, 5.0))
        
        self.in_manual_start.delete(0, "end")
        self.in_manual_start.insert(0, "0.00")
        self.in_manual_end.delete(0, "end")
        self.in_manual_end.insert(0, f"{min(self.manual_duration, 5.0):.2f}")
        
        # Update duration text
        diff = min(self.manual_duration, 5.0)
        self.lbl_manual_duration.configure(text=f"─Éß╗Ö d├ái ─æoß║ín cß║»t: {diff:.2f}s")
        
        # Populate default save path
        if self.active_project_slug:
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            self.in_manual_save_dir.delete(0, "end")
            self.in_manual_save_dir.insert(0, os.path.abspath(folders["clips"]))
        else:
            fallback_dir = os.path.abspath(os.path.join(os.getcwd(), "clips"))
            self.in_manual_save_dir.delete(0, "end")
            self.in_manual_save_dir.insert(0, fallback_dir)

        # Enable buttons
        self.btn_manual_cut.configure(state="normal")
        
        # Show first frame
        self.update_manual_preview(0.0)

    def update_manual_preview(self, t):
        if not self.manual_cap or not self.manual_cap.isOpened():
            return
            
        frame_no = int(t * self.manual_fps)
        total_frames = int(self.manual_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_no = max(0, min(total_frames - 1, frame_no))
        
        self.manual_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = self.manual_cap.read()
        if ret:
            # Convert BGR to RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h_v, w_v, _ = rgb.shape
            
            # Target box max dimensions
            max_box_w = 480
            max_box_h = 430
            
            current_ratio = w_v / h_v
            if current_ratio > (max_box_w / max_box_h): # wider
                target_w = max_box_w
                target_h = int(target_w / current_ratio)
            else: # taller
                target_h = max_box_h
                target_w = int(target_h * current_ratio)
                
            # Resize image
            pil_img = Image.fromarray(rgb)
            pil_img = pil_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
            self.manual_preview_label.configure(image=ctk_img, text="")
            self.manual_preview_label.image = ctk_img

    def on_manual_start_slider_move(self, val):
        val = round(float(val), 2)
        end_val = round(float(self.slider_manual_end.get()), 2)
        
        if val > end_val:
            val = end_val
            self.slider_manual_start.set(val)
            
        self.in_manual_start.delete(0, "end")
        self.in_manual_start.insert(0, f"{val:.2f}")
        
        diff = end_val - val
        self.lbl_manual_duration.configure(text=f"─Éß╗Ö d├ái ─æoß║ín cß║»t: {diff:.2f}s")
        self.update_manual_preview(val)
        
    def on_manual_end_slider_move(self, val):
        val = round(float(val), 2)
        start_val = round(float(self.slider_manual_start.get()), 2)
        
        if val < start_val:
            val = start_val
            self.slider_manual_end.set(val)
            
        self.in_manual_end.delete(0, "end")
        self.in_manual_end.insert(0, f"{val:.2f}")
        
        diff = val - start_val
        self.lbl_manual_duration.configure(text=f"─Éß╗Ö d├ái ─æoß║ín cß║»t: {diff:.2f}s")
        self.update_manual_preview(val)

    def adjust_manual_time(self, target, delta):
        if not self.manual_video_path:
            return
            
        if target == "start":
            curr = float(self.slider_manual_start.get())
            new_val = max(0.0, min(self.manual_duration, curr + delta))
            end_val = float(self.slider_manual_end.get())
            if new_val > end_val:
                new_val = end_val
            self.slider_manual_start.set(new_val)
            self.on_manual_start_slider_move(new_val)
        else:
            curr = float(self.slider_manual_end.get())
            new_val = max(0.0, min(self.manual_duration, curr + delta))
            start_val = float(self.slider_manual_start.get())
            if new_val < start_val:
                new_val = start_val
            self.slider_manual_end.set(new_val)
            self.on_manual_end_slider_move(new_val)

    def on_manual_entry_update(self, target):
        if not self.manual_video_path:
            return
            
        try:
            if target == "start":
                val = float(self.in_manual_start.get())
                val = max(0.0, min(self.manual_duration, val))
                end_val = float(self.slider_manual_end.get())
                if val > end_val:
                    val = end_val
                self.slider_manual_start.set(val)
                self.on_manual_start_slider_move(val)
            else:
                val = float(self.in_manual_end.get())
                val = max(0.0, min(self.manual_duration, val))
                start_val = float(self.slider_manual_start.get())
                if val < start_val:
                    val = start_val
                self.slider_manual_end.set(val)
                self.on_manual_end_slider_move(val)
        except ValueError:
            if target == "start":
                val = self.slider_manual_start.get()
                self.in_manual_start.delete(0, "end")
                self.in_manual_start.insert(0, f"{val:.2f}")
            else:
                val = self.slider_manual_end.get()
                self.in_manual_end.delete(0, "end")
                self.in_manual_end.insert(0, f"{val:.2f}")

    def manual_browse_save_dir(self):
        curr_dir = self.in_manual_save_dir.get().strip()
        if not curr_dir or not os.path.exists(curr_dir):
            curr_dir = os.path.abspath(os.getcwd())
            if self.active_project_slug:
                folders = self.project_manager.get_project_folders(self.active_project_slug)
                curr_dir = folders["clips"]
                
        target_dir = filedialog.askdirectory(
            initialdir=curr_dir,
            title="Chß╗ìn Th╞░ Mß╗Ñc L╞░u Clips"
        )
        if target_dir:
            self.in_manual_save_dir.delete(0, "end")
            self.in_manual_save_dir.insert(0, os.path.abspath(target_dir))

    def start_manual_cut(self):
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn hoß║╖c tß║ío dß╗▒ ├ín tr╞░ß╗¢c.")
            return
            
        if not self.manual_video_path:
            return
            
        start_t = float(self.slider_manual_start.get())
        end_t = float(self.slider_manual_end.get())
        duration = end_t - start_t
        
        if duration <= 0.1:
            messagebox.showerror("Khoß║úng thß╗¥i gian lß╗ùi", "─Éß╗Ö d├ái ─æoß║ín cß║»t phß║úi lß╗¢n h╞ín 0.1s.")
            return
            
        save_dir = self.in_manual_save_dir.get().strip()
        if not save_dir:
            messagebox.showerror("Thiß║┐u ─æ╞░ß╗¥ng dß║½n", "Vui l├▓ng nhß║¡p hoß║╖c chß╗ìn th╞░ mß╗Ñc l╞░u clip.")
            return
            
        self.btn_manual_cut.configure(state="disabled", text="─Éang cß║»t...")
        self.manual_progress_bar.set(0.1)
        self.manual_console.clear()
        
        export_vertical = self.cb_manual_vertical_var.get() == "on"
        mute_audio = self.cb_manual_mute_var.get() == "on"
        
        t = threading.Thread(target=self.run_manual_cut_thread, args=(start_t, end_t, export_vertical, mute_audio, save_dir), daemon=True)
        t.start()
        
    def run_manual_cut_thread(self, start_t, end_t, export_vertical, mute_audio, save_dir):
        try:
            self.manual_console.log("[*] Khß╗ƒi tß║ío quy tr├¼nh cß║»t video thß╗º c├┤ng...")
            self.manual_console.log(f"[*] Th╞░ mß╗Ñc l╞░u kß║┐t quß║ú: {save_dir}")
            
            # Call backend cut clip helper
            result = cut_single_clip(
                mat_path=self.manual_video_path,
                clips_dir=save_dir,
                product_slug=self.active_project_slug,
                start_t=start_t,
                end_t=end_t,
                export_vertical=export_vertical,
                mute_audio=mute_audio,
                analyze_quality=True,
                log_callback=self.manual_console.log
            )
            
            # Save to metadata
            meta = self.active_project_meta
            if "clips" not in meta:
                meta["clips"] = []
            meta["clips"].append(result)
            self.project_manager.save_metadata(self.active_project_slug, meta)
            
            self.manual_progress_bar.set(1.0)
            self.manual_console.log("[+] Ho├án th├ánh cß║»t clip thß╗º c├┤ng!")
            
            # Notify main thread
            self.after(0, lambda: self.finish_manual_cut(result))
            
        except Exception as e:
            self.manual_console.log(f"[x] Lß╗ùi cß║»t video: {e}")
            self.after(0, self.on_manual_cut_failed)
            
    def finish_manual_cut(self, result):
        self.btn_manual_cut.configure(state="normal", text="Bß║»t ─Éß║ºu Cß║»t & L╞░u Clip")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú cß║»t v├á l╞░u clip th├ánh c├┤ng:\n{os.path.basename(result['file_path'])}")
        
    def on_manual_cut_failed(self):
        self.btn_manual_cut.configure(state="normal", text="Bß║»t ─Éß║ºu Cß║»t & L╞░u Clip")
        self.manual_progress_bar.set(0.0)
        messagebox.showerror("Lß╗ùi cß║»t", "Cß║»t clip thß╗º c├┤ng thß║Ñt bß║íi. Xem chi tiß║┐t lß╗ùi ß╗ƒ bß║úng nhß║¡t k├╜.")

    def on_app_closing(self):
        if hasattr(self, 'manual_cap') and self.manual_cap:
            try:
                self.manual_cap.release()
            except Exception:
                pass
        self.destroy()

    def build_tab_script(self):
        tab = self.tab_flow2.tab("≡ƒô¥ Kß╗ïch Bß║ún")
        tab.grid_columnconfigure(0, weight=1)
        
        row_style = ctk.CTkFrame(tab, fg_color="transparent")
        row_style.pack(fill="x", padx=20, pady=(15, 8))
        
        lbl_style = ctk.CTkLabel(row_style, text="Chß╗ìn phong c├ích kß╗ïch bß║ún:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_style.pack(side="left")
        
        self.script_style_combo = ctk.CTkComboBox(row_style, values=list(SCRIPT_STYLES.keys()), width=250, state="readonly")
        self.script_style_combo.pack(side="left", padx=15)
        self.script_style_combo.set("Mß╗ƒ ─æß║ºu t├▓ m├▓")
        
        self.btn_gen_script = ctk.CTkButton(row_style, text="Viß║┐t kß╗ïch bß║ún mß╗¢i (AI Gemini)", command=self.generate_project_script, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_gen_script.pack(side="left", padx=10)
        
        # Row for learned template selection
        row_learned = ctk.CTkFrame(tab, fg_color="transparent")
        row_learned.pack(fill="x", padx=20, pady=(0, 10))
        
        lbl_learned = ctk.CTkLabel(row_learned, text="Hß╗ìc theo phong c├ích video:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_learned.pack(side="left")
        
        self.script_learned_combo = ctk.CTkComboBox(row_learned, values=["Kh├┤ng ├íp dß╗Ñng"], width=420, state="readonly")
        self.script_learned_combo.pack(side="left", padx=15)
        self.script_learned_combo.set("Kh├┤ng ├íp dß╗Ñng")
        
        btn_refresh_learned = ctk.CTkButton(
            row_learned, text="≡ƒöä L├ám mß╗¢i", width=80, **secondary_button_kwargs(),
            command=self.script_refresh_learned_dropdown
        )
        btn_refresh_learned.pack(side="left")
        
        # Script box Labeled
        self.script_display_box = LabeledTextbox(tab, "Lß╗¥i thoß║íi Thuyß║┐t minh (D├╣ng nß║íp giß╗ìng ─æß╗ìc ElevenLabs):", height=240)
        self.script_display_box.pack(fill="both", expand=True, padx=20, pady=5)
        
        row_footer = ctk.CTkFrame(tab, fg_color="transparent")
        row_footer.pack(fill="x", padx=20, pady=15)
        
        self.btn_copy_script = ctk.CTkButton(row_footer, text="Sao ch├⌐p kß╗ïch bß║ún v├áo Clipboard", command=self.copy_script_to_clipboard, height=35)
        self.btn_copy_script.pack(side="left")

        # Initialize and populate learned dropdown choices
        self.kb_slug_mapping = {}
        self.script_refresh_learned_dropdown()

    def script_refresh_learned_dropdown(self):
        """Tß║úi danh s├ích c├íc video ─æ├ú hß╗ìc v├á hiß╗ân thß╗ï v├áo combobox kß╗ïch bß║ún."""
        learned_list = kb.load_learned_list()
        self.kb_slug_mapping = {}
        choices = ["Kh├┤ng ├íp dß╗Ñng"]
        
        for item in learned_list:
            display_name = f"[{item.get('platform', 'N/A')}] {item.get('title', 'B├ái hß╗ìc')}"
            choices.append(display_name)
            self.kb_slug_mapping[display_name] = item.get("slug")
            
        self.script_learned_combo.configure(values=choices)
        
        # Reset if current selection is invalid
        current = self.script_learned_combo.get()
        if current not in choices:
            self.script_learned_combo.set("Kh├┤ng ├íp dß╗Ñng")

    def build_tab_audio(self):
        tab = self.tab_flow2.tab("≡ƒÄÖ∩╕Å Giß╗ìng ─Éß╗ìc")
        tab.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(tab, text="Thuyß║┐t Minh AI (TTS) ΓÇö Kh├┤ng cß║ºn ElevenLabs",
                           font=ctk.CTkFont(size=15, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(20, 6))

        # ΓöÇΓöÇ TTS AUTO SECTION ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
        tts_frame = ctk.CTkFrame(tab, fg_color="#1a2435", corner_radius=10,
                                 border_width=1, border_color="#334155")
        tts_frame.pack(fill="x", padx=20, pady=(6, 10))

        ctk.CTkLabel(tts_frame,
                     text="≡ƒÄñ  Tß║ío Giß╗ìng ─Éß╗ìc Tß╗▒ ─Éß╗Öng (Edge TTS ΓÇö Miß╗àn Ph├¡)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#7dd3fc").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(tts_frame,
                     text="Chß╗ìn giß╗ìng ΓåÆ ─Éiß╗üu chß╗ënh tß╗æc ─æß╗Ö ΓåÆ Nhß║Ñn 'Tß║ío' ΓåÆ voice.mp3 sß║╡n s├áng cho dß╗▒ng video",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=14, pady=(0, 8))

        # Voice selector row
        voice_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        voice_row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(voice_row, text="Giß╗ìng ─æß╗ìc:",
                     font=ctk.CTkFont(size=12), width=100).pack(side="left")
        self.tts_voice_var = ctk.StringVar(value="HoaiMy (Nß╗» miß╗ün Bß║»c)")
        self.tts_voice_menu = ctk.CTkOptionMenu(
            voice_row,
            values=[
                "HoaiMy (Nß╗» miß╗ün Bß║»c)",
                "NamMinh (Nam miß╗ün Bß║»c)",
            ],
            variable=self.tts_voice_var,
            width=220,
        )
        self.tts_voice_menu.pack(side="left", padx=8)
        ctk.CTkLabel(voice_row, text="*Edge TTS miß╗àn ph├¡, kh├┤ng cß║ºn API key",
                     font=ctk.CTkFont(size=10), text_color="#4ade80").pack(side="left", padx=8)

        # Speed slider row
        speed_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        speed_row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(speed_row, text="Tß╗æc ─æß╗Ö:",
                     font=ctk.CTkFont(size=12), width=100).pack(side="left")
        self.tts_speed_var = ctk.DoubleVar(value=1.1)
        speed_slider = ctk.CTkSlider(speed_row, from_=0.7, to=1.5,
                                     variable=self.tts_speed_var, width=180,
                                     command=lambda v: self.tts_speed_lbl.configure(
                                         text=f"{v:.1f}x"))
        speed_slider.pack(side="left", padx=8)
        self.tts_speed_lbl = ctk.CTkLabel(speed_row, text="1.1x",
                                          font=ctk.CTkFont(size=12), width=45)
        self.tts_speed_lbl.pack(side="left")
        ctk.CTkLabel(speed_row, text="(0.7 = chß║¡m, 1.0 = b├¼nh th╞░ß╗¥ng, 1.5 = nhanh)",
                     font=ctk.CTkFont(size=10), text_color="#64748b").pack(side="left", padx=6)

        # Script preview box
        ctk.CTkLabel(tts_frame, text="Nß╗Öi dung thuyß║┐t minh (lß║Ñy tß╗▒ ─æß╗Öng tß╗½ kß╗ïch bß║ún hoß║╖c nhß║¡p tay):",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=14, pady=(6, 2))
        self.tts_text_box = ctk.CTkTextbox(tts_frame, height=100, font=ctk.CTkFont(size=12))
        self.tts_text_box.pack(fill="x", padx=14, pady=(0, 6))
        self.tts_text_box.insert("1.0", "Nhß║¡p lß╗¥i thuyß║┐t minh v├áo ─æ├óy, hoß║╖c bß║Ñm 'Lß║Ñy tß╗½ kß╗ïch bß║ún' ─æß╗â tß╗▒ ─æß╗Öng nß║íp...")

        # Buttons row
        tts_btn_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_btn_row.pack(fill="x", padx=14, pady=(4, 12))

        ctk.CTkButton(tts_btn_row, text="≡ƒô¥ Lß║Ñy tß╗½ Kß╗ïch bß║ún",
                      command=self._tts_load_from_script,
                      height=32, width=160,
                      fg_color="#1e40af", hover_color="#1d4ed8").pack(side="left", padx=4)

        ctk.CTkButton(tts_btn_row, text="≡ƒÄñ Tß║ío Giß╗ìng ─Éß╗ìc",
                      command=self._tts_generate,
                      height=32, width=160,
                      fg_color="#7c3aed", hover_color="#6d28d9").pack(side="left", padx=4)

        self.tts_status_lbl = ctk.CTkLabel(tts_btn_row, text="",
                                           font=ctk.CTkFont(size=11),
                                           text_color="#4ade80")
        self.tts_status_lbl.pack(side="left", padx=8)

        # TTS progress bar
        self.tts_progress = ctk.CTkProgressBar(tts_frame, height=6)
        self.tts_progress.pack(fill="x", padx=14, pady=(0, 10))
        self.tts_progress.set(0)

        # ΓöÇΓöÇ MANUAL IMPORT SECTION (kept for backward compat) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
        ctk.CTkLabel(tab,
                     text="ΓÇö Hoß║╖c import file MP3 thß╗º c├┤ng (ElevenLabs/CapCut/kh├íc) ΓÇö",
                     font=ctk.CTkFont(size=11), text_color="#475569").pack(pady=(8, 4))
        
        row_import = ctk.CTkFrame(tab, fg_color="transparent")
        row_import.pack(fill="x", padx=20, pady=8)
        
        self.btn_import_audio = ctk.CTkButton(row_import, text="Chß╗ìn & Import File MP3",
                                              command=self.import_voice_audio, height=35,
                                              fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_import_audio.pack(side="left")
        
        self.lbl_audio_status = ctk.CTkLabel(row_import, text="Ch╞░a nß║íp ├óm thanh (.mp3)",
                                             font=ctk.CTkFont(size=13, weight="bold"),
                                             text_color="#ef4444")
        self.lbl_audio_status.pack(side="left", padx=20)
        
        self.lbl_audio_duration = ctk.CTkLabel(tab,
                                               text="─Éß╗Ö d├ái ├óm thanh thuyß║┐t minh: Ch╞░a ─æo",
                                               font=ctk.CTkFont(size=12))
        self.lbl_audio_duration.pack(anchor="w", padx=20, pady=5)

    def _tts_load_from_script(self):
        """Load voiceover text from project's voice_script.txt."""
        proj = self.get_current_project_folders()
        if not proj:
            return
        script_path = os.path.join(proj["scripts"], "voice_script.txt")
        if not os.path.exists(script_path):
            messagebox.showwarning("Kh├┤ng c├│ kß╗ïch bß║ún",
                                   "Ch╞░a c├│ voice_script.txt. H├úy tß║ío kß╗ïch bß║ún tr╞░ß╗¢c.")
            return
        with open(script_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        self.tts_text_box.delete("1.0", "end")
        self.tts_text_box.insert("1.0", text)
        self.tts_status_lbl.configure(text="Γ£ô ─É├ú tß║úi kß╗ïch bß║ún")

    def _tts_generate(self):
        """Generate TTS voice file from text in tts_text_box."""
        text = self.tts_text_box.get("1.0", "end-1c").strip()
        if not text or "Nhß║¡p lß╗¥i thuyß║┐t minh" in text:
            messagebox.showwarning("Thiß║┐u nß╗Öi dung",
                                   "Nhß║¡p hoß║╖c tß║úi kß╗ïch bß║ún tr╞░ß╗¢c khi tß║ío giß╗ìng ─æß╗ìc.")
            return

        proj = self.get_current_project_folders()
        if not proj:
            messagebox.showerror("Lß╗ùi", "Ch╞░a chß╗ìn dß╗▒ ├ín. H├úy tß║ío hoß║╖c chß╗ìn dß╗▒ ├ín tr╞░ß╗¢c.")
            return

        voice_map = {
            "HoaiMy (Nß╗» miß╗ün Bß║»c)": "HoaiMy",
            "NamMinh (Nam miß╗ün Bß║»c)": "NamMinh",
        }
        voice = voice_map.get(self.tts_voice_var.get(), "HoaiMy")
        speed = self.tts_speed_var.get()
        output_path = os.path.join(proj["audio"], "voice.mp3")

        self.tts_status_lbl.configure(text="ΓÅ│ ─Éang tß║ío giß╗ìng ─æß╗ìc...", text_color="#fbbf24")
        self.tts_progress.set(0.1)
        self.update()

        def run_tts():
            try:
                from tools.tts_engine import synthesize
                out = synthesize(text, voice=voice, speed=speed, output_path=output_path)
                size_kb = os.path.getsize(out) / 1024
                self.after(0, lambda: self._tts_done(out, size_kb))
            except Exception as e:
                self.after(0, lambda: self._tts_error(str(e)))

        import threading
        threading.Thread(target=run_tts, daemon=True).start()

    def _tts_done(self, path, size_kb):
        self.tts_progress.set(1.0)
        self.tts_status_lbl.configure(
            text=f"Γ£ô ─É├ú tß║ío! ({size_kb:.0f} KB)",
            text_color="#4ade80")
        self.lbl_audio_status.configure(text="Γ£ô voice.mp3 sß║╡n s├áng (TTS)", text_color="#4ade80")
        from editor.audio_helper import get_audio_duration
        dur = get_audio_duration(path)
        self.lbl_audio_duration.configure(text=f"─Éß╗Ö d├ái ├óm thanh: {dur:.1f} gi├óy")
        messagebox.showinfo("Γ£à TTS Ho├án Tß║Ñt",
                            f"File voice.mp3 ─æ├ú ─æ╞░ß╗úc tß║ío!\n{path}\n\n"
                            f"K├¡ch th╞░ß╗¢c: {size_kb:.0f} KB | Thß╗¥i l╞░ß╗úng: {dur:.1f}s\n"
                            f"Sß║╡n s├áng ─æß╗â dß╗▒ng video trong Tab 'Dß╗▒ng video'.")

    def _tts_error(self, err):
        self.tts_progress.set(0)
        self.tts_status_lbl.configure(text=f"Γ¥î Lß╗ùi: {err[:50]}", text_color="#ef4444")
        messagebox.showerror("Lß╗ùi TTS", f"Kh├┤ng thß╗â tß║ío giß╗ìng ─æß╗ìc:\n{err}")

    def _refresh_router_status(self):
        """Update AI Router provider status dots in settings tab."""
        try:
            from core.ai_router import get_router
            status = get_router().get_status()
            color_map = {
                "active":       ("#22c55e", "active"),
                "busy":         ("#f59e0b", "busy"),
                "rate_limited": ("#ef4444", "rate limited"),
                "no_key":       ("#334155", "no key"),
            }
            for pid, (dot, lbl) in self.router_status_labels.items():
                info = status.get(pid, {})
                st = info.get("status", "no_key")
                color, text = color_map.get(st, ("#334155", st))
                dot.configure(text_color=color)
                if st == "rate_limited":
                    retry = info.get("retry_in", "?")
                    lbl.configure(text=f"{text} ({retry}s)", text_color=color)
                elif st == "active":
                    rpm = info.get("rpm_limit", "?")
                    used = info.get("requests_last_60s", 0)
                    lbl.configure(text=f"{text} ({used}/{rpm} rpm)", text_color=color)
                else:
                    lbl.configure(text=text, text_color=color)
        except Exception as e:
            pass


    def build_tab_editor(self):
        tab = self.tab_flow1.tab("≡ƒÄ¼ Dß╗▒ng video")

        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)
        
        left_frame = ctk.CTkFrame(tab, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        right_frame = ctk.CTkFrame(tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # Left Panel (Settings)
        lbl_sett = ctk.CTkLabel(left_frame, text="Cß║Ñu H├¼nh Dß╗▒ng Video:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_sett.pack(anchor="w", pady=4)
        
        self.cb_subtitles_var = ctk.StringVar(value="on")
        self.cb_subtitles = ctk.CTkCheckBox(left_frame, text="Bß║¡t phß╗Ñ ─æß╗ü chß╗» (Tß╗▒ ─æß╗Öng theo kß╗ïch bß║ún)", variable=self.cb_subtitles_var, onvalue="on", offvalue="off")
        self.cb_subtitles.pack(anchor="w", pady=8)
        
        self.lbl_editor_summary = ctk.CTkLabel(left_frame, text="Th├┤ng tin ph├┤i hiß╗çn c├│:\n- Video ph├┤i: 0\n- Thuyß║┐t minh: Ch╞░a c├│", justify="left")
        self.lbl_editor_summary.pack(anchor="w", pady=15)
        
        self.btn_edit_video = ctk.CTkButton(left_frame, text="Bß║»t ─Éß║ºu Dß╗▒ng Video TikTok (9:16)", command=self.start_video_editor_pipeline, height=40, fg_color="#10b981", hover_color="#059669")
        self.btn_edit_video.pack(fill="x", pady=10)
        
        # Right Panel (Console)
        lbl_log = ctk.CTkLabel(right_frame, text="Nhß║¡t k├╜ render video (moviepy):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_log.pack(anchor="w", pady=4)
        
        self.editor_console = ConsoleView(right_frame)
        self.editor_console.pack(fill="both", expand=True)

    def build_tab_results(self):
        tab = self.tab_flow1.tab("Γ£à Kß║┐t quß║ú")
        tab.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(tab, text="Kß║┐t Quß║ú Xuß║Ñt Video & ─É─âng B├ái", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(15, 10))
        
        self.lbl_video_result_status = ctk.CTkLabel(tab, text="Video ch╞░a ─æ╞░ß╗úc dß╗▒ng. Vui l├▓ng ho├án th├ánh Tab 'Dß╗▒ng video'.", font=ctk.CTkFont(size=13), text_color="#e2e8f0")
        self.lbl_video_result_status.pack(anchor="w", padx=20, pady=5)
        
        row_act = ctk.CTkFrame(tab, fg_color="transparent")
        row_act.pack(fill="x", padx=20, pady=10)
        
        self.btn_open_export_dir = ctk.CTkButton(row_act, text="Mß╗ƒ Th╞░ Mß╗Ñc Chß╗⌐a Video", command=self.open_export_dir, **secondary_button_kwargs(), state="disabled")
        self.btn_open_export_dir.pack(side="left")
        
        # Caption & Hashtags to easily copy
        self.caption_display_box = LabeledTextbox(tab, "Caption gß╗úi ├╜ ─æß╗â copy ─æ─âng TikTok:", height=70)
        self.caption_display_box.pack(fill="x", padx=20, pady=5)
        
        self.hashtags_display_box = LabeledTextbox(tab, "Hashtags gß╗úi ├╜ ─æß╗â copy:", height=50)
        self.hashtags_display_box.pack(fill="x", padx=20, pady=5)

    def build_tab_storyboard(self):
        tab = self.tab_flow2.tab("≡ƒû╝∩╕Å Storyboard")
        
        # Left Panel (options/config) and Right Panel (results/console)
        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)
        
        opt_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        opt_scroll.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        right_frame = ctk.CTkFrame(tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        # Mode selector at the top
        lbl_mode = ctk.CTkLabel(opt_scroll, text="Chß║┐ ─æß╗Ö Storyboard AI:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_mode.pack(anchor="w", pady=(2, 4))
        
        self.sb_mode_combo = ctk.CTkComboBox(
            opt_scroll, 
            values=["Tß║ío tß╗½ v─ân bß║ún (Text)", "Tr├¡ch xuß║Ñt tß╗½ video mß║½u"],
            command=self.on_sb_mode_changed,
            state="readonly",
            height=30
        )
        self.sb_mode_combo.pack(fill="x", pady=(0, 10))
        self.sb_mode_combo.set("Tß║ío tß╗½ v─ân bß║ún (Text)")
        
        # --- FRAME 1: TEXT MODE ---
        self.sb_text_mode_frame = ctk.CTkFrame(opt_scroll, fg_color="transparent")
        self.sb_text_mode_frame.pack(fill="x", expand=True)
        
        lbl_info = ctk.CTkLabel(self.sb_text_mode_frame, text="Th├┤ng tin sß║ún phß║⌐m:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_info.pack(anchor="w", pady=(2, 4))
        
        self.sb_prod_name = LabeledEntry(self.sb_text_mode_frame, "T├¬n sß║ún phß║⌐m *", "M├íy t─âm n╞░ß╗¢c cß║ºm tay")
        self.sb_prod_name.pack(fill="x", pady=2)
        
        self.sb_prod_desc = LabeledTextbox(self.sb_text_mode_frame, "M├┤ tß║ú sß║ún phß║⌐m", height=60)
        self.sb_prod_desc.pack(fill="x", pady=2)
        
        self.sb_prod_usp = LabeledEntry(self.sb_text_mode_frame, "─Éiß╗âm b├ín h├áng ch├¡nh (USP)", "V├¡ dß╗Ñ: ├üp lß╗▒c phun mß║ính, pin tr├óu")
        self.sb_prod_usp.pack(fill="x", pady=2)
        
        self.sb_prod_pain = LabeledEntry(self.sb_text_mode_frame, "Nß╗ùi ─æau kh├ích h├áng (Pain points)", "V├¡ dß╗Ñ: Hay chß║úy m├íu n╞░ß╗¢u r─âng, dß║»t thß╗⌐c ─ân")
        self.sb_prod_pain.pack(fill="x", pady=2)
        
        self.sb_prod_audience = LabeledEntry(self.sb_text_mode_frame, "─Éß╗æi t╞░ß╗úng ng╞░ß╗¥i xem", "V├¡ dß╗Ñ: Giß╗¢i trß║╗ niß╗üng r─âng, d├ón v─ân ph├▓ng")
        self.sb_prod_audience.pack(fill="x", pady=2)
        
        div = ctk.CTkFrame(self.sb_text_mode_frame, height=2, fg_color="#2d2d34")
        div.pack(fill="x", pady=10)
        
        lbl_dir = ctk.CTkLabel(self.sb_text_mode_frame, text="─Éß╗ïnh h╞░ß╗¢ng video & AI Prompts:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_dir.pack(anchor="w", pady=(2, 4))
        
        self.sb_video_style = LabeledEntry(self.sb_text_mode_frame, "Phong c├ích video quß║úng c├ío", "V├¡ dß╗Ñ: TikTok review sß║ún phß║⌐m ch├ón thß║¡t...")
        self.sb_video_style.pack(fill="x", pady=2)
        self.sb_video_style.set("TikTok review sß║ún phß║⌐m ch├ón thß║¡t, quay cß║¡n cß║únh thao t├íc tay, ├ính s├íng s├íng sß║ích, nhß╗ïp nhanh")
        
        row_dur = ctk.CTkFrame(self.sb_text_mode_frame, fg_color="transparent")
        row_dur.pack(fill="x", pady=2)
        row_dur.grid_columnconfigure(0, weight=1)
        row_dur.grid_columnconfigure(1, weight=1)
        
        self.sb_duration = LabeledEntry(row_dur, "Thß╗¥i l╞░ß╗úng (gi├óy)", "24")
        self.sb_duration.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.sb_duration.set("24")
        
        self.sb_scene_count = LabeledEntry(row_dur, "Sß╗æ ph├ón cß║únh", "6")
        self.sb_scene_count.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.sb_scene_count.set("6")
        
        self.sb_background = LabeledEntry(self.sb_text_mode_frame, "Bß╗æi cß║únh / Background mong muß╗æn", "V├¡ dß╗Ñ: Ph├▓ng tß║»m hiß╗çn ─æß║íi, tß╗æi giß║ún")
        self.sb_background.pack(fill="x", pady=2)
        self.sb_background.set("Ph├▓ng kh├ích studio ß║Ñm ├íp, sß║ích sß║╜")
        
        self.sb_product_image_note = LabeledEntry(self.sb_text_mode_frame, "Ghi ch├║ ß║únh sß║ún phß║⌐m tham chiß║┐u", "V├¡ dß╗Ñ: M├áu trß║»ng sß╗⌐, c├│ logo chß╗» nß╗òi")
        self.sb_product_image_note.pack(fill="x", pady=2)
        self.sb_product_image_note.set("Cß║¡n cß║únh cß║ºm tr├¬n tay, r├╡ chi tiß║┐t c├íc n├║t bß║Ñm")
        
        self.sb_background_image_note = LabeledEntry(self.sb_text_mode_frame, "Ghi ch├║ ß║únh background tham chiß║┐u", "V├¡ dß╗Ñ: Kß╗ç gß╗ù sß╗ôi s├íng m├áu, c├óy xanh nhß╗Å")
        self.sb_background_image_note.pack(fill="x", pady=2)
        self.sb_background_image_note.set("M├áu gß╗ù s├íng, tß╗æi giß║ún, c├│ c├óy xanh nh├▓e mß╗¥ ph├¡a sau")
        
        lbl_target = ctk.CTkLabel(self.sb_text_mode_frame, text="C├┤ng cß╗Ñ AI Video ─æ├¡ch:", font=ctk.CTkFont(size=11))
        lbl_target.pack(anchor="w", pady=(5, 2))
        self.sb_prompt_target = ctk.CTkComboBox(
            self.sb_text_mode_frame, 
            values=["Google Labs / Veo", "ChatGPT image generation", "Gemini image/video", "Generic AI video prompt"],
            state="readonly",
            height=28
        )
        self.sb_prompt_target.pack(fill="x", pady=(0, 5))
        self.sb_prompt_target.set("Google Labs / Veo")
        
        # --- FRAME 2: VIDEO MODE ---
        self.sb_video_mode_frame = ctk.CTkFrame(opt_scroll, fg_color="transparent")
        # sb_video_mode_frame will not be packed on startup
        
        lbl_vid_title = ctk.CTkLabel(self.sb_video_mode_frame, text="Ph├ón t├¡ch video mß║½u ─æß╗â tr├¡ch xuß║Ñt prompt:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_vid_title.pack(anchor="w", pady=(2, 4))
        
        row_sel_vid = ctk.CTkFrame(self.sb_video_mode_frame, fg_color="transparent")
        row_sel_vid.pack(fill="x", pady=2)
        row_sel_vid.grid_columnconfigure(0, weight=1)
        
        self.sb_sample_video_path = LabeledEntry(row_sel_vid, "─É╞░ß╗¥ng dß║½n tß╗çp video mß║½u *", "Chß╗ìn file video tß╗½ m├íy t├¡nh...")
        self.sb_sample_video_path.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        btn_browse_vid = ctk.CTkButton(row_sel_vid, text="Chß╗ìn video", command=self.browse_sample_video, width=80, height=28)
        btn_browse_vid.grid(row=0, column=1, sticky="s", pady=(18, 0))
        
        lbl_vid_target = ctk.CTkLabel(self.sb_video_mode_frame, text="C├┤ng cß╗Ñ AI Video ─æ├¡ch nhß║»m tß╗¢i:", font=ctk.CTkFont(size=11))
        lbl_vid_target.pack(anchor="w", pady=(10, 2))
        self.sb_video_prompt_target = ctk.CTkComboBox(
            self.sb_video_mode_frame, 
            values=["Google Labs / Veo", "Luma Dream Machine", "Runway Gen-3", "OpenAI Sora", "Generic AI video prompt"],
            state="readonly",
            height=28
        )
        self.sb_video_prompt_target.pack(fill="x", pady=(0, 5))
        self.sb_video_prompt_target.set("Google Labs / Veo")
        
        # Custom action entry
        lbl_custom_action = ctk.CTkLabel(self.sb_video_mode_frame, text="M├┤ tß║ú h├ánh ─æß╗Öng trong video (Tiß║┐ng Viß╗çt - T├╣y chß╗ìn):", font=ctk.CTkFont(size=11))
        lbl_custom_action.pack(anchor="w", pady=(10, 2))
        self.sb_custom_action = ctk.CTkEntry(
            self.sb_video_mode_frame,
            placeholder_text="V├¡ dß╗Ñ: tay cß║ºm gi├í ─æß╗í ─æiß╗çn thoß║íi gß║¡p l├¬n xuß╗æng, xoay v├▓ng...",
            height=28
        )
        self.sb_custom_action.pack(fill="x", pady=(0, 5))
        
        # Offline mode checkbox
        self.sb_offline_only = ctk.CTkCheckBox(
            self.sb_video_mode_frame,
            text="Chß╗ë ph├ón t├¡ch ngoß║íi tuyß║┐n (Kh├┤ng gß╗ìi Gemini API)",
            font=ctk.CTkFont(size=11)
        )
        self.sb_offline_only.pack(fill="x", pady=(8, 5))
        
        # Right Panel: Buttons, Preview, and Console
        row_btns = ctk.CTkFrame(right_frame, fg_color="transparent")
        row_btns.pack(fill="x", pady=(0, 5))
        
        self.btn_gen_sb = ctk.CTkButton(row_btns, text="Tß║ío storyboard", command=self.start_storyboard_generation, width=130, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_gen_sb.pack(side="left", padx=4)
        
        self.btn_extract_prompt = ctk.CTkButton(row_btns, text="Tr├¡ch xuß║Ñt prompt", command=self.start_prompt_extraction, width=130, fg_color="#8b5cf6", hover_color="#7c3aed")
        # btn_extract_prompt is not packed initially
        
        self.btn_save_sb = ctk.CTkButton(row_btns, text="L╞░u kß║┐t quß║ú", command=self.save_storyboard, width=130, fg_color="#10b981", hover_color="#059669")
        self.btn_save_sb.pack(side="left", padx=4)
        
        self.btn_open_sb_dir = ctk.CTkButton(row_btns, text="Mß╗ƒ th╞░ mß╗Ñc", command=self.open_storyboard_dir, width=110, **secondary_button_kwargs())
        self.btn_open_sb_dir.pack(side="left", padx=4)
        
        # Copy Buttons Row
        row_copy = ctk.CTkFrame(right_frame, fg_color="transparent")
        row_copy.pack(fill="x", pady=5)
        
        self.btn_copy_all_sb = ctk.CTkButton(row_copy, text="Copy to├án bß╗Ö kß║┐t quß║ú", command=self.copy_all_storyboard, width=140, height=28, font=ctk.CTkFont(size=11))
        self.btn_copy_all_sb.pack(side="left", padx=3)
        
        self.btn_copy_img_p = ctk.CTkButton(row_copy, text="Copy prompt ß║únh", command=self.copy_image_prompts, width=120, height=28, font=ctk.CTkFont(size=11))
        self.btn_copy_img_p.pack(side="left", padx=3)
        
        self.btn_copy_vid_p = ctk.CTkButton(row_copy, text="Copy prompt video", command=self.copy_video_prompts, width=120, height=28, font=ctk.CTkFont(size=11))
        self.btn_copy_vid_p.pack(side="left", padx=3)

        self.btn_export_prompts = ctk.CTkButton(
            row_copy, text="≡ƒôñ Xuß║Ñt Prompts Pack", command=self.export_prompts_from_storyboard,
            width=150, height=28, font=ctk.CTkFont(size=11),
            fg_color="#10b981", hover_color="#059669"
        )
        self.btn_export_prompts.pack(side="left", padx=3)

        # Markdown Preview area
        lbl_prev = ctk.CTkLabel(right_frame, text="Bß║ún xem tr╞░ß╗¢c storyboard.md:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_prev.pack(anchor="w", pady=(5, 2))
        
        self.sb_preview_box = ctk.CTkTextbox(right_frame, height=260)
        self.sb_preview_box.pack(fill="both", expand=True, pady=(0, 10))
        self.sb_preview_box.configure(state="disabled")
        
        # Console Log
        lbl_console = ctk.CTkLabel(right_frame, text="Nhß║¡t k├╜ Storyboard AI:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_console.pack(anchor="w", pady=(0, 2))
        
        self.storyboard_console = ConsoleView(right_frame, height=100)
        self.storyboard_console.pack(fill="x")

    # ==================== AGENT JOBS TAB ====================

    # ==================== AGENT JOBS TAB ====================

    def build_tab_agent_jobs(self):
        tab = self.tab_flow2.tab("ΓÜÖ∩╕Å C├┤ng Viß╗çc AI")
        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Agent Jobs Manager", font=ctk.CTkFont(size=16, weight="bold"), text_color="#60a5fa").pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(left, text="Tß║ío h├áng ─æß╗úi t├íc vß╗Ñ cho Antigravity/Codex hoß║╖c Worker tß╗▒ ─æß╗Öng.", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left").pack(anchor="w", pady=(0, 12))

        self.agent_source_box = LabeledTextbox(left, "TikTok link / video path", height=80)
        self.agent_source_box.pack(fill="x", pady=5)

        ctk.CTkButton(left, text="Chß╗ìn video local", command=self.agent_select_video, height=30, **secondary_button_kwargs()).pack(fill="x", pady=(0, 10))

        self.agent_target_mode = ctk.CTkComboBox(left, values=["Create new project", "Append to active/existing project"], state="readonly")
        self.agent_target_mode.pack(fill="x", pady=5)
        self.agent_target_mode.set("Create new project")

        ctk.CTkLabel(left, text="Engine", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 4))
        self.agent_engine = ctk.CTkComboBox(left, values=["ai_studio", "html_video", "mixed", "capcut", "upgrade_audit"], state="readonly")
        self.agent_engine.pack(fill="x", pady=5)
        self.agent_engine.set("ai_studio")

        self.agent_new_project_name = LabeledEntry(left, "T├¬n dß╗▒ ├ín mß╗¢i (t├╣y chß╗ìn)", "Bß╗Å trß╗æng ─æß╗â hß╗ç thß╗æng tß╗▒ ─æß║╖t t├¬n")
        self.agent_new_project_name.pack(fill="x", pady=5)

        ctk.CTkLabel(left, text="Dß╗▒ ├ín hiß╗çn c├│", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 4))
        self.agent_project_combo = ctk.CTkComboBox(left, values=["No project"], state="readonly")
        self.agent_project_combo.pack(fill="x", pady=5)

        row = ctk.CTkFrame(left, fg_color="transparent")
        row.pack(fill="x", pady=(2, 10))
        ctk.CTkButton(row, text="L├ám mß╗¢i dß╗▒ ├ín", command=self.agent_refresh_projects, height=28, **secondary_button_kwargs()).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(row, text="D├╣ng dß╗▒ ├ín hiß╗çn tß║íi", command=self.agent_use_active_project, height=28, **secondary_button_kwargs()).pack(side="left", fill="x", expand=True, padx=(4, 0))

        ctk.CTkLabel(left, text="Danh s├ích T├íc vß╗Ñ (Tasks)", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(8, 4))
        self.agent_task_vars = {}
        task_labels = {
            "analyze_video": "Ph├ón t├¡ch nß╗Öi dung video mß║½u",
            "write_script": "Soß║ín kß╗ïch bß║ún review / b├ín h├áng",
            "write_image_prompts": "Tß║ío prompt h├¼nh ß║únh 9:16",
            "write_voiceover": "Tß║ío v─ân bß║ún thuyß║┐t minh sß║ích",
            "write_capcut_plan": "Tß║ío kß║┐ hoß║ích dß╗▒ng video CapCut",
        }
        for task in DEFAULT_TASKS:
            var = ctk.BooleanVar(value=True)
            self.agent_task_vars[task] = var
            ctk.CTkCheckBox(left, text=task_labels.get(task, task), variable=var).pack(anchor="w", pady=2)

        self.agent_duration = LabeledEntry(left, "Thß╗¥i l╞░ß╗úng mß╗Ñc ti├¬u (gi├óy)", "45")
        self.agent_duration.pack(fill="x", pady=(10, 5))
        self.agent_duration.set("45")

        self.agent_notes = LabeledTextbox(left, "Ghi ch├║ y├¬u cß║ºu cho Worker", height=80)
        self.agent_notes.pack(fill="x", pady=5)

        ctk.CTkButton(left, text="≡ƒÜÇ Tß║ío Job cho Antigravity / Codex", command=self.agent_create_job, height=38, fg_color="#10b981", hover_color="#059669", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(12, 5))

        # Right side: ChatGPT / Gemini Style Live Monitor Tabview
        self.agent_right_tabview = ctk.CTkTabview(right, corner_radius=8)
        self.agent_right_tabview.grid(row=0, column=0, sticky="nsew")

        tab_monitor = self.agent_right_tabview.add("≡ƒñû Tiß║┐n Tr├¼nh Live (AI Monitor)")
        tab_logs = self.agent_right_tabview.add("≡ƒô¥ Worker Prompt & System Logs")

        # Configure Tab 1: Live Monitor
        tab_monitor.grid_columnconfigure(0, weight=1)
        tab_monitor.grid_rowconfigure(2, weight=1)

        # Job Selection & Status Header
        header_frame = ctk.CTkFrame(tab_monitor, fg_color="#1e1e24", corner_radius=6)
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        ctk.CTkLabel(header_frame, text="Chß╗ìn Job theo d├╡i:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 5), pady=8)
        self.agent_job_select_combo = ctk.CTkComboBox(header_frame, values=["Ch╞░a c├│ Job n├áo"], command=self.on_agent_job_selected, state="readonly", width=220)
        self.agent_job_select_combo.pack(side="left", padx=5, pady=8)

        self.agent_job_status_badge = ctk.CTkLabel(header_frame, text="READY", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#3b82f6", text_color="white", corner_radius=4, padx=8, pady=2)
        self.agent_job_status_badge.pack(side="right", padx=10, pady=8)

        # Progress bar
        self.agent_job_progressbar = ctk.CTkProgressBar(tab_monitor, height=8, corner_radius=4)
        self.agent_job_progressbar.grid(row=1, column=0, sticky="ew", padx=5, pady=(2, 8))
        self.agent_job_progressbar.set(0.0)

        # Task Checklist Frame (ChatGPT Thinking Style)
        self.agent_checklist_frame = ctk.CTkScrollableFrame(tab_monitor, height=140, fg_color="#141418", corner_radius=6)
        self.agent_checklist_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        
        # Artifact Output Viewer Section
        art_frame = ctk.CTkFrame(tab_monitor, fg_color="transparent")
        art_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=(5, 2))
        ctk.CTkLabel(art_frame, text="Xem Sß║ún Phß║⌐m ─Éß║ºu Ra:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        
        self.agent_artifact_btns_frame = ctk.CTkFrame(art_frame, fg_color="transparent")
        self.agent_artifact_btns_frame.pack(fill="x", pady=2)

        self.agent_output_viewer = ctk.CTkTextbox(tab_monitor, height=180, corner_radius=6, border_width=1, border_color="#3a3a3a")
        self.agent_output_viewer.grid(row=4, column=0, sticky="ew", padx=5, pady=(0, 5))

        # Configure Tab 2: Logs & Worker Prompt
        tab_logs.grid_columnconfigure(0, weight=1)
        tab_logs.grid_rowconfigure(1, weight=1)
        tab_logs.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(tab_logs, text="Worker Prompt (Copy cho Antigravity/Codex):", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w", pady=(5, 2))
        self.agent_prompt_preview = ctk.CTkTextbox(tab_logs, height=160, corner_radius=6, border_width=1, border_color="#3a3a3a")
        self.agent_prompt_preview.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        ctk.CTkLabel(tab_logs, text="Hß╗ç thß╗æng Nhß║¡t k├╜ (System Logs):", font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, sticky="sw", pady=(0, 2))
        self.agent_jobs_console = ConsoleView(tab_logs, height=140)
        self.agent_jobs_console.grid(row=3, column=0, sticky="nsew")

        row_actions = ctk.CTkFrame(tab_logs, fg_color="transparent")
        row_actions.grid(row=4, column=0, sticky="ew", pady=(8, 5))
        ctk.CTkButton(row_actions, text="L├ám mß╗¢i danh s├ích", command=self.agent_refresh_jobs, height=30, **secondary_button_kwargs()).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(row_actions, text="Sao ch├⌐p Worker Prompt", command=self.agent_copy_worker_prompt, height=30, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"]).pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.agent_project_display_to_slug = {}
        self.agent_jobs_cache = {}
        self.agent_selected_job_id = None

        self.agent_refresh_projects()
        self.agent_refresh_jobs()
        self.start_agent_jobs_auto_refresh()

    def agent_select_video(self):
        path = filedialog.askopenfilename(
            title="Choose video file",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"), ("All files", "*.*")]
        )
        if path:
            self.agent_source_box.set(path)

    def agent_refresh_projects(self):
        projects = self.project_manager.list_projects()
        self.agent_project_display_to_slug = {}
        values = []
        for project in projects:
            display = f"{project['name']} ({project['slug']})"
            self.agent_project_display_to_slug[display] = project["slug"]
            values.append(display)
        if not values:
            values = ["No project"]
        self.agent_project_combo.configure(values=values)
        if self.active_project_slug:
            for display, slug in self.agent_project_display_to_slug.items():
                if slug == self.active_project_slug:
                    self.agent_project_combo.set(display)
                    return
        self.agent_project_combo.set(values[0])

    def agent_use_active_project(self):
        if not self.active_project_slug:
            messagebox.showwarning("No active project", "Please load or create a project first.")
            return
        self.agent_target_mode.set("Append to active/existing project")
        self.agent_refresh_projects()

    def agent_create_job(self):
        source_value = self.agent_source_box.get().strip()
        if not source_value:
            messagebox.showwarning("Missing source", "Please paste a TikTok link or choose a local video.")
            return

        selected_tasks = [task for task, var in self.agent_task_vars.items() if var.get()]
        if not selected_tasks:
            messagebox.showwarning("Missing tasks", "Please choose at least one task.")
            return

        try:
            duration_seconds = int(self.agent_duration.get().strip() or "45")
        except ValueError:
            messagebox.showerror("Invalid duration", "Target duration must be a number.")
            return

        mode_label = self.agent_target_mode.get()
        target_mode = "append_existing" if mode_label.startswith("Append") else "create_new"
        target_slug = None
        if target_mode == "append_existing":
            display = self.agent_project_combo.get()
            target_slug = self.agent_project_display_to_slug.get(display)
            if not target_slug:
                messagebox.showwarning("Missing project", "Please choose an existing project.")
                return

        try:
            job = self.agent_job_manager.create_job(
                source_value=source_value,
                target_mode=target_mode,
                target_project_slug=target_slug,
                new_project_name=self.agent_new_project_name.get().strip(),
                tasks=selected_tasks,
                style={
                    "language": "vi",
                    "video_format": "vertical_tiktok",
                    "duration_seconds": duration_seconds,
                    "notes": self.agent_notes.get().strip(),
                },
                engine=self.agent_engine.get().strip() or "ai_studio",
            )
        except Exception as exc:
            messagebox.showerror("Create job failed", str(exc))
            return

        self.agent_jobs_console.log(f"[+] Created {job['job_id']}")
        self.agent_jobs_console.log(f"    Project: {job['target']['project_slug']}")
        self.agent_jobs_console.log(f"    Inbox: {job['paths']['job_file']}")
        self.agent_jobs_console.log(f"    Worker prompt: {job['paths']['worker_prompt']}")
        self.agent_jobs_console.log(f"    Manifest: {job['paths'].get('manifest_file', '')}")
        self.agent_prompt_preview.delete("1.0", "end")
        try:
            prompt_path = job["paths"].get("manifest_worker_prompt") or job["paths"]["worker_prompt"]
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.agent_prompt_preview.insert("1.0", f.read())
        except Exception:
            self.agent_prompt_preview.insert("1.0", job["paths"]["worker_prompt"])

        self.active_project_slug = job["target"]["project_slug"]
        self.load_project_list()
        self.load_project_details(self.active_project_slug)
        self.agent_refresh_projects()
        self.agent_refresh_jobs()
        messagebox.showinfo("Agent job created", f"Created job:\n{job['job_id']}\n\nOpen the worker prompt in Antigravity/Codex or let Job Worker process it.")

    def start_agent_jobs_auto_refresh(self):
        """Periodically refresh jobs UI in background every 3 seconds."""
        def _loop():
            try:
                self.agent_refresh_jobs(silent=True)
            except Exception:
                pass
            self.after(3000, _loop)
        self.after(3000, _loop)

    def agent_refresh_jobs(self, silent=False):
        if not hasattr(self, "agent_jobs_console"):
            return
        if not silent:
            self.agent_jobs_console.clear()
            self.agent_jobs_console.log(f"Jobs root: {self.agent_job_manager.jobs_root}")
        
        jobs = self.agent_job_manager.list_jobs(limit=30)
        combo_values = []
        self.agent_jobs_cache = {}

        if not jobs:
            if not silent:
                self.agent_jobs_console.log("No jobs yet.")
            self.agent_job_select_combo.configure(values=["Ch╞░a c├│ Job n├áo"])
            self.agent_job_select_combo.set("Ch╞░a c├│ Job n├áo")
            return

        for job in jobs:
            jid = job["job_id"]
            st = job["status"]
            pslug = job["project_slug"]
            engine = job.get("engine", "")
            progress = job.get("progress", {})
            progress_text = ""
            if progress:
                progress_text = f" {progress.get('done', 0)}/{progress.get('total', 0)}"
            display_str = f"[{st.upper()}] {jid}{progress_text} ({engine or pslug})"
            combo_values.append(display_str)
            self.agent_jobs_cache[display_str] = job
            if not silent:
                self.agent_jobs_console.log(f"[{st.upper()}] {jid} | {engine or pslug} | {progress_text.strip()}")

        self.agent_job_select_combo.configure(values=combo_values)
        if not self.agent_selected_job_id or not any(self.agent_selected_job_id in v for v in combo_values):
            self.agent_job_select_combo.set(combo_values[0])
            self.on_agent_job_selected(combo_values[0])
        else:
            # Refresh current selected display
            for v in combo_values:
                if self.agent_selected_job_id in v:
                    self.agent_job_select_combo.set(v)
                    self.on_agent_job_selected(v)
                    break

    def on_agent_job_selected(self, choice=None):
        if not choice or choice == "Ch?a c? Job n?o":
            return

        summary_info = self.agent_jobs_cache.get(choice)
        if not summary_info:
            return

        job_id = summary_info["job_id"]
        self.agent_selected_job_id = job_id

        manifest_view = None
        job_data = None
        try:
            manifest_view = self.agent_job_manager.load_manifest_job(job_id, sync=True)
        except Exception:
            manifest_view = None

        if manifest_view:
            job_data = manifest_view["manifest"]
            status = job_data.get("status", "pending").lower()
            tasks = manifest_view.get("tasks", [])
            output_dir = Path(manifest_view["job_dir"]) / "artifacts"
            artifact_entries = manifest_view.get("artifacts", [])
            prompt_path = Path(manifest_view["job_dir"]) / "worker_prompt.md"
            if prompt_path.exists():
                self.agent_prompt_preview.delete("1.0", "end")
                try:
                    self.agent_prompt_preview.insert("1.0", prompt_path.read_text(encoding="utf-8"))
                except Exception:
                    self.agent_prompt_preview.insert("1.0", str(prompt_path))
        else:
            # Legacy fallback for older .agent_jobs entries.
            for folder in [self.agent_job_manager.inbox_dir, self.agent_job_manager.processing_dir, self.agent_job_manager.outbox_dir, self.agent_job_manager.failed_dir]:
                for p in folder.glob(f"*{job_id}*.json"):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            job_data = json.load(f)
                            break
                    except Exception:
                        pass
                if job_data:
                    break
            if not job_data:
                job_data = summary_info
            status = job_data.get("status", "pending").lower()
            tasks = job_data.get("tasks", DEFAULT_TASKS)
            output_dir = Path(job_data.get("target", {}).get("output_dir", ""))
            artifact_entries = []

        status_colors = {
            "pending": ("CHO XU LY", "#eab308"),
            "planning": ("DANG LAP KE HOACH", "#a855f7"),
            "running": ("DANG XU LY", "#3b82f6"),
            "processing": ("DANG XU LY", "#3b82f6"),
            "completed": ("HOAN THANH", "#10b981"),
            "done": ("HOAN THANH", "#10b981"),
            "failed": ("THAT BAI", "#ef4444"),
        }
        badge_text, badge_color = status_colors.get(status, (status.upper(), "#6b7280"))
        self.agent_job_status_badge.configure(text=badge_text, fg_color=badge_color)

        existing_files = set()
        if output_dir.exists():
            existing_files = {p.name for p in output_dir.glob("*")}

        for child in self.agent_checklist_frame.winfo_children():
            child.destroy()

        task_titles = {
            "analyze_video": "Phan tich video mau",
            "write_script": "Soan kich ban review/ban hang",
            "write_image_prompts": "Tao prompt hinh anh 9:16",
            "write_voiceover": "Tao van ban thuyet minh",
            "write_capcut_plan": "Tao ke hoach dung CapCut",
        }
        legacy_output_map = {
            "analyze_video": "analysis.md",
            "write_script": "script.md",
            "write_image_prompts": "image_prompts.md",
            "write_voiceover": "voiceover.txt",
            "write_capcut_plan": "capcut_plan.md",
        }

        completed_count = 0
        total_tasks = len(tasks)
        for task in tasks:
            row = ctk.CTkFrame(self.agent_checklist_frame, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=5)

            if isinstance(task, dict):
                title = task.get("name") or task.get("task_id", "")
                task_status = (task.get("status") or "pending").lower()
                output_file = task.get("output_file", "")
                if output_file and output_file in existing_files and task_status != "failed":
                    task_status = "done"
                detail = f" -> {output_file}" if output_file else ""
            else:
                title = task_titles.get(task, task)
                output_file = legacy_output_map.get(task, "")
                detail = f" -> {output_file}" if output_file else ""
                task_status = "done" if status in ["done", "completed"] else "pending"
                if status == "processing":
                    task_status = "done" if output_file in existing_files else "running"

            if task_status in ["done", "completed", "skipped"]:
                icon = "[done]"
                color = "#10b981"
                completed_count += 1
            elif task_status == "running":
                icon = "[run]"
                color = "#60a5fa"
            elif task_status == "failed" or status == "failed":
                icon = "[fail]"
                color = "#ef4444"
            else:
                icon = "[wait]"
                color = "#94a3b8"

            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=12)).pack(side="left", padx=(5, 8))
            ctk.CTkLabel(row, text=f"{title}{detail}", font=ctk.CTkFont(size=12), text_color=color).pack(side="left")

        progress_pct = (completed_count / total_tasks) if total_tasks > 0 else 0.0
        if status in ["done", "completed"]:
            progress_pct = 1.0
        self.agent_job_progressbar.set(progress_pct)

        for child in self.agent_artifact_btns_frame.winfo_children():
            child.destroy()

        if output_dir.exists():
            artifact_files = [item.get("name") for item in artifact_entries if item.get("name")]
            if not artifact_files:
                artifact_files = [p.name for p in output_dir.glob("*") if p.name != "job.json"]
            if artifact_files:
                for fname in artifact_files:
                    btn = ctk.CTkButton(
                        self.agent_artifact_btns_frame,
                        text=fname,
                        height=26,
                        fg_color="#2e2e38",
                        hover_color="#3b82f6",
                        font=ctk.CTkFont(size=11),
                        command=lambda f=fname, d=output_dir: self.load_agent_output_file(d / f),
                    )
                    btn.pack(side="left", padx=3, pady=2)
            else:
                ctk.CTkLabel(self.agent_artifact_btns_frame, text="Dang cho Worker tao artifact...", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=5)
        else:
            ctk.CTkLabel(self.agent_artifact_btns_frame, text="Chua co thu muc artifact.", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=5)

    def load_agent_output_file(self, file_path):
        """Display content of selected output artifact file in viewer textbox."""
        self.agent_output_viewer.delete("1.0", "end")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.agent_output_viewer.insert("1.0", content)
        except Exception as e:
            self.agent_output_viewer.insert("1.0", f"Lß╗ùi ─æß╗ìc file: {e}")

    def agent_copy_worker_prompt(self):
        text = self.agent_prompt_preview.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Empty prompt", "Create a job first, then copy the worker prompt.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Worker prompt copied to clipboard.")
    def build_tab_settings(self):
        """Deprecated: functionality merged into build_tab_settings_merged."""
        pass


    def build_tab_prompt_compiler(self):
        """Deprecated: functionality merged into build_tab_settings_merged."""
        pass


    def build_tab_learning_review(self):
        """Deprecated: functionality merged into build_tab_learn_and_review."""
        pass


    def refresh_learning_reviews(self):
        if not hasattr(self, "learning_review_scroll"):
            return
            
        for widget in self.learning_review_scroll.winfo_children():
            widget.destroy()
            
        items = self.learning_review_store.list_pending()
        self.learning_review_items = {item["name"]: item for item in items}
        self.review_card_frames = {}
        
        if not items:
            lbl = ctk.CTkLabel(
                self.learning_review_scroll,
                text="Ch╞░a c├│ ─æß╗ü xuß║Ñt n├áo cß║ºn duyß╗çt.\nHß╗ç thß╗æng ─æang vß║¡n h├ánh ß╗òn ─æß╗ïnh.",
                font=font(12),
                text_color=COLORS["subtle"]
            )
            lbl.pack(pady=40)
            self.on_learning_review_selected(None)
            return

        # Render list (newest first)
        for item in reversed(items):
            name = item["name"]
            path = item.get("path", "")
            
            # Card frame
            card = ctk.CTkFrame(self.learning_review_scroll, fg_color="#1e1e24", corner_radius=8, border_width=0)
            card.pack(fill="x", padx=5, pady=4)
            card.grid_columnconfigure(0, weight=1)
            self.review_card_frames[name] = card
            
            # Proposal title
            ctk.CTkLabel(
                card,
                text=name,
                font=font(12, "bold"),
                anchor="w",
                wraplength=200,
                justify="left"
            ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
            
            # Subtitle/Meta (File size or modification date)
            meta_text = "─Éß╗ü xuß║Ñt hß╗ìc hß╗Åi mß╗¢i"
            if path and os.path.exists(path):
                try:
                    sz = os.path.getsize(path)
                    meta_text = f"Dung l╞░ß╗úng: {sz} bytes"
                except Exception:
                    pass
            
            ctk.CTkLabel(
                card,
                text=meta_text,
                font=font(10),
                text_color=COLORS["muted"],
                anchor="w"
            ).grid(row=1, column=0, padx=10, pady=(0, 8), sticky="w")
            
            # Actions row
            act_row = ctk.CTkFrame(card, fg_color="transparent")
            act_row.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
            
            # Select/View button
            ctk.CTkButton(
                act_row,
                text="Xem chi tiß║┐t",
                width=90,
                height=24,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#051016",
                font=font(10, "bold"),
                command=lambda n=name: self.on_learning_review_selected(n)
            ).pack(side="left", padx=(0, 5))

        # Select first proposal by default
        if items:
            first_name = list(self.learning_review_items.keys())[0]
            if not self.current_review_selection or self.current_review_selection not in self.learning_review_items:
                self.on_learning_review_selected(first_name)
            else:
                self.on_learning_review_selected(self.current_review_selection)

    def on_learning_review_selected(self, choice=None):
        if not hasattr(self, "learning_review_tabs"):
            return
            
        for tb in self.review_textboxes.values():
            tb.delete("1.0", "end")
            
        if hasattr(self, "lbl_preview_title"):
            self.lbl_preview_title.configure(text="≡ƒôä Xem Chi Tiß║┐t ─Éß╗ü Xuß║Ñt")
            self.btn_approve_review.grid()
            self.btn_reject_review.grid()
            
        if not choice:
            self.current_review_selection = None
            self.review_textboxes["T├│m tß║»t"].insert("1.0", "Ch╞░a c├│ proposal n├áo trong knowledge_base/review_queue.\n\nWorker/Codex c├│ thß╗â ghi lesson hoß║╖c prompt proposal v├áo folder n├áy ─æß╗â anh duyß╗çt.")
            return
            
        self.current_review_selection = choice
        content = self.learning_review_store.read(choice) or "(Empty proposal)"
        
        import re
        if "### C├┤ng cß╗Ñ & Kh├íi niß╗çm:" in content:
            parts = re.split(r'### C├┤ng cß╗Ñ & Kh├íi niß╗çm:|### Quy tr├¼nh:|### ß╗¿ng dß╗Ñng cho Hermes:', content)
            summary_part = parts[0].strip() if len(parts) >= 1 else content
            concepts_part = parts[1].strip() if len(parts) >= 2 else ""
            workflow_part = parts[2].strip() if len(parts) >= 3 else ""
            analysis_combined = f"πÇÉ C├öNG Cß╗ñ & KH├üI NIß╗åM πÇæ\n{concepts_part}\n\nπÇÉ QUY TR├îNH πÇæ\n{workflow_part}"
            hermes_part = parts[3].strip() if len(parts) >= 4 else "Kh├┤ng c├│ dß╗» liß╗çu."
            
            self.review_textboxes["T├│m tß║»t"].insert("1.0", summary_part)
            self.review_textboxes["Ph├ón t├¡ch"].insert("1.0", analysis_combined)
            self.review_textboxes["Setup"].insert("1.0", f"πÇÉ ß╗¿NG Dß╗ñNG CHO HERMES πÇæ\n{hermes_part}")
            self.review_textboxes["Prompt"].insert("1.0", "Loß║íi Knowledge Proposal n├áy kh├┤ng c├│ Prompt Mapping cß╗Ñ thß╗â.")
        else:
            parts = re.split(r'### Ph├ón t├¡ch Hook/Body/CTA:|### Quay dß╗▒ng & Setup:|### Prompt Mapping:', content)
            summary_part = parts[0].strip() if len(parts) >= 1 else content
            analysis_part = parts[1].strip() if len(parts) >= 2 else "Kh├┤ng c├│ dß╗» liß╗çu ph├ón t├¡ch."
            setup_part = parts[2].strip() if len(parts) >= 3 else "Kh├┤ng c├│ dß╗» liß╗çu setup."
            prompt_part = parts[3].strip() if len(parts) >= 4 else "Kh├┤ng c├│ dß╗» liß╗çu prompt."
            
            self.review_textboxes["T├│m tß║»t"].insert("1.0", summary_part)
            self.review_textboxes["Ph├ón t├¡ch"].insert("1.0", analysis_part)
            self.review_textboxes["Setup"].insert("1.0", setup_part)
            self.review_textboxes["Prompt"].insert("1.0", prompt_part)

    def approve_learning_review(self):
        name = getattr(self, "current_review_selection", None)
        if not name:
            messagebox.showinfo("Learning review", "Vui l├▓ng chß╗ìn mß╗Öt ─æß╗ü xuß║Ñt ─æß╗â duyß╗çt.")
            return
        try:
            target = self.learning_review_store.approve(name)
            messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú duyß╗çt v├á l╞░u b├ái hß╗ìc th├ánh c├┤ng!")
            self.current_review_selection = None
            self.refresh_learning_reviews()
        except Exception as exc:
            messagebox.showerror("Approve failed", str(exc))

    def reject_learning_review(self):
        name = getattr(self, "current_review_selection", None)
        if not name:
            messagebox.showinfo("Learning review", "Vui l├▓ng chß╗ìn mß╗Öt ─æß╗ü xuß║Ñt ─æß╗â tß╗½ chß╗æi.")
            return
        try:
            target = self.learning_review_store.reject(name)
            messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú tß╗½ chß╗æi ─æß╗ü xuß║Ñt n├áy.")
            self.current_review_selection = None
            self.refresh_learning_reviews()
        except Exception as exc:
            messagebox.showerror("Reject failed", str(exc))

    def build_tab_idea_engine(self):
        """Tab Idea Engine ΓÇö AI gß╗úi ├╜ angle video, user tick chß╗ìn."""
        tab = self.tab_flow2.tab("≡ƒÆí ├¥ T╞░ß╗ƒng")
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=7)
        tab.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Controls ---
        left = ctk.CTkScrollableFrame(tab, fg_color="transparent", width=260)
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        ctk.CTkLabel(left, text="≡ƒÆí Idea Engine", font=ctk.CTkFont(size=16, weight="bold"), text_color="#60a5fa").pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(left, text="AI sinh & chß║Ñm ─æiß╗âm angle video\nUser tick chß╗ìn ─æß╗â triß╗ân khai", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left").pack(anchor="w", pady=(0, 12))

        # Sß╗æ ideas
        row_n = ctk.CTkFrame(left, fg_color="transparent")
        row_n.pack(fill="x", pady=4)
        ctk.CTkLabel(row_n, text="Sß╗æ ├╜ t╞░ß╗ƒng muß╗æn AI tß║ío:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.idea_num_var = ctk.StringVar(value="15")
        ctk.CTkEntry(row_n, textvariable=self.idea_num_var, width=45, height=26).pack(side="right")

        # Generate button
        self.btn_gen_ideas = ctk.CTkButton(
            left, text="≡ƒñû AI Tß║ío ├¥ T╞░ß╗ƒng", command=self.start_idea_generation,
            height=36, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_gen_ideas.pack(fill="x", pady=(8, 4))

        # Auto-select shortcuts
        ctk.CTkLabel(left, text="Chß╗ìn nhanh theo ─æiß╗âm cao:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(12, 4))
        row_auto = ctk.CTkFrame(left, fg_color="transparent")
        row_auto.pack(fill="x", pady=2)
        row_auto.grid_columnconfigure(0, weight=1)
        row_auto.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(row_auto, text="Γ£à Top 3", command=lambda: self.auto_select_top_n(3),
                      height=30, fg_color="#10b981", hover_color="#059669").grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkButton(row_auto, text="Γ£à Top 5", command=lambda: self.auto_select_top_n(5),
                      height=30, fg_color="#10b981", hover_color="#059669").grid(row=0, column=1, padx=(4, 0), sticky="ew")

        ctk.CTkButton(left, text="Γ¼£ Bß╗Å chß╗ìn tß║Ñt cß║ú", command=self.deselect_all_ideas,
                      height=28, **secondary_button_kwargs()).pack(fill="x", pady=(4, 12))

        # Divider
        ctk.CTkFrame(left, height=1, fg_color="#2d2d34").pack(fill="x", pady=8)

        # Save selected
        self.btn_save_angles = ctk.CTkButton(
            left, text="≡ƒÆ╛ L╞░u Angle ─É├ú Chß╗ìn", command=self.save_selected_angles_action,
            height=36, fg_color="#8b5cf6", hover_color="#7c3aed",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_save_angles.pack(fill="x", pady=4)

        self.btn_to_storyboard = ctk.CTkButton(
            left, text="≡ƒôï Mß╗ƒ Storyboard AI", command=lambda: (self.switch_flow(2), self.tab_flow2.set("≡ƒû╝∩╕Å Storyboard")),
            height=32, **secondary_button_kwargs()
        )
        self.btn_to_storyboard.pack(fill="x", pady=4)

        # Stats label
        self.idea_stats_lbl = ctk.CTkLabel(left, text="Ch╞░a c├│ ├╜ t╞░ß╗ƒng n├áo", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left")
        self.idea_stats_lbl.pack(anchor="w", pady=(12, 4))

        # Console
        ctk.CTkLabel(left, text="Nhß║¡t k├╜:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(8, 2))
        self.idea_console = ConsoleView(left, height=120)
        self.idea_console.pack(fill="x")

        # --- Right Panel: Idea Card List ---
        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        row_hdr = ctk.CTkFrame(right, fg_color="transparent")
        row_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ctk.CTkLabel(row_hdr, text="Danh s├ích angle gß╗úi ├╜ tß╗½ AI (tick chß╗ìn ─æß╗â triß╗ân khai):", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.idea_selected_lbl = ctk.CTkLabel(row_hdr, text="─É├ú chß╗ìn: 0", font=ctk.CTkFont(size=12), text_color="#10b981")
        self.idea_selected_lbl.pack(side="right", padx=10)

        self.idea_cards_frame = ctk.CTkScrollableFrame(right, fg_color="#121214", corner_radius=8)
        self.idea_cards_frame.grid(row=1, column=0, sticky="nsew")
        self.idea_cards_frame.grid_columnconfigure(0, weight=1)

        self.idea_placeholder_lbl = ctk.CTkLabel(
            self.idea_cards_frame,
            text="Ch╞░a c├│ ├╜ t╞░ß╗ƒng n├áo.\nNhß║Ñn '≡ƒñû AI Tß║ío ├¥ T╞░ß╗ƒng' ─æß╗â bß║»t ─æß║ºu.",
            font=ctk.CTkFont(size=13), text_color="#4b5563"
        )
        self.idea_placeholder_lbl.pack(pady=60)

    # --- IDEA ENGINE ACTIONS ---

    def start_idea_generation(self):
        """Gß╗ìi Gemini AI tß║ío danh s├ích ideas."""
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn hoß║╖c tß║ío dß╗▒ ├ín tr╞░ß╗¢c.")
            return
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a cß║Ñu h├¼nh GEMINI_API_KEY.")
            return

        try:
            num_ideas = int(self.idea_num_var.get().strip())
        except ValueError:
            num_ideas = 15

        meta = self.active_project_meta or {}
        self.btn_gen_ideas.configure(state="disabled", text="ΓÅ│ ─Éang tß║ío ├╜ t╞░ß╗ƒng...")
        self.idea_console.clear()
        self.idea_console.log("[*] ─Éang gß╗ìi Gemini AI tß║ío angle ideas...")

        def run():
            result = generate_ideas(
                product_name=meta.get("product_name", ""),
                description=meta.get("description", ""),
                price=meta.get("price", ""),
                selling_points=meta.get("selling_points", ""),
                target_audience=meta.get("target_audience", ""),
                pain_points=meta.get("pain_points", ""),
                color_material=meta.get("color_material", ""),
                video_context=meta.get("video_context", ""),
                image_style=meta.get("image_style", ""),
                num_ideas=num_ideas,
            )
            self.after(0, lambda: self.finish_idea_generation(result))

        threading.Thread(target=run, daemon=True).start()

    def finish_idea_generation(self, result):
        """Xß╗¡ l├╜ kß║┐t quß║ú tß╗½ AI v├á render cards."""
        self.btn_gen_ideas.configure(state="normal", text="≡ƒñû AI Tß║ío ├¥ T╞░ß╗ƒng")

        if "error" in result:
            self.idea_console.log(f"[x] Lß╗ùi: {result['error']}")
            messagebox.showerror("Lß╗ùi API", result["error"])
            return

        ideas = result.get("ideas", [])
        if not ideas:
            self.idea_console.log("[!] AI kh├┤ng trß║ú vß╗ü ├╜ t╞░ß╗ƒng n├áo.")
            return

        self.current_ideas_data = result

        # Save to project
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        save_ideas(folders["root"], result)
        self.idea_console.log(f"[+] Tß║ío th├ánh c├┤ng {len(ideas)} ├╜ t╞░ß╗ƒng. ─É├ú l╞░u ideas.json")
        self.idea_stats_lbl.configure(text=f"Tß╗òng: {len(ideas)} angle")

        self._render_idea_cards(ideas)

    def _render_idea_cards(self, ideas):
        """Render idea cards v├áo scrollable frame."""
        # Clear old cards
        for widget in self.idea_cards_frame.winfo_children():
            widget.destroy()
        self.idea_checkboxes.clear()

        if not ideas:
            ctk.CTkLabel(self.idea_cards_frame, text="Kh├┤ng c├│ ├╜ t╞░ß╗ƒng.", text_color="#4b5563").pack(pady=40)
            return

        # Sort by total_score desc
        ideas_sorted = sorted(ideas, key=lambda x: x.get("total_score", 0), reverse=True)

        STATUS_COLORS = {
            "Dß╗à": "#10b981",
            "Trung b├¼nh": "#f59e0b",
            "Kh├│": "#ef4444",
        }

        for idx, idea in enumerate(ideas_sorted):
            var = ctk.BooleanVar(value=False)
            self.idea_checkboxes.append((idea, var))

            # Card frame
            card = ctk.CTkFrame(self.idea_cards_frame, fg_color="#1e1e24", corner_radius=8)
            card.pack(fill="x", padx=8, pady=4)
            card.grid_columnconfigure(1, weight=1)

            # Checkbox
            rank_lbl = ctk.CTkLabel(card, text=f"#{idx+1}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#60a5fa", width=30)
            rank_lbl.grid(row=0, column=0, padx=(10, 4), pady=12, sticky="nw")

            cb = ctk.CTkCheckBox(
                card, text="", variable=var, width=20,
                command=self._update_selected_count
            )
            cb.grid(row=0, column=0, padx=(35, 0), pady=12, sticky="nw")

            # Content
            content = ctk.CTkFrame(card, fg_color="transparent")
            content.grid(row=0, column=1, padx=4, pady=8, sticky="ew")
            content.grid_columnconfigure(0, weight=1)

            # Title + type row
            title_row = ctk.CTkFrame(content, fg_color="transparent")
            title_row.pack(fill="x")
            ctk.CTkLabel(title_row, text=idea.get("title", ""), font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(side="left")

            diff = idea.get("difficulty", "")
            diff_color = STATUS_COLORS.get(diff, "#94a3b8")
            ctk.CTkLabel(title_row, text=f"  {diff}", font=ctk.CTkFont(size=11), text_color=diff_color).pack(side="left", padx=8)

            angle_type = idea.get("angle_type", "")
            ctk.CTkLabel(title_row, text=angle_type, font=ctk.CTkFont(size=10), text_color="#94a3b8", fg_color="#2d2d3a", corner_radius=4).pack(side="right", padx=(4, 0))

            # Description
            desc = idea.get("description", "")
            if desc:
                ctk.CTkLabel(content, text=desc, font=ctk.CTkFont(size=11), text_color="#cbd5e1", wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(2, 4))

            # Scene flow
            flow = idea.get("scene_flow", "")
            if flow:
                ctk.CTkLabel(content, text=f"≡ƒô╜ {flow}", font=ctk.CTkFont(size=10), text_color="#6b7280", wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(0, 4))

            # Scores row
            scores_row = ctk.CTkFrame(content, fg_color="transparent")
            scores_row.pack(fill="x", pady=(2, 0))

            score_defs = [
                ("≡ƒÄ¼ AI Video", "ai_video_score"),
                ("≡ƒô╕ Demo", "demo_score"),
                ("≡ƒÆ░ Sell", "sell_score"),
                ("ΓÖ╗∩╕Å Reuse", "reuse_score"),
                ("≡ƒô▒ TikTok", "tiktok_fit"),
                ("Γ¡É Total", "total_score"),
            ]

            for label, key in score_defs:
                val = idea.get(key, 0)
                color = "#10b981" if val >= 80 else "#f59e0b" if val >= 60 else "#ef4444"
                score_box = ctk.CTkFrame(scores_row, fg_color="#111118", corner_radius=4)
                score_box.pack(side="left", padx=(0, 4), pady=2)
                ctk.CTkLabel(score_box, text=f"{label}", font=ctk.CTkFont(size=9), text_color="#6b7280").pack(padx=4, pady=(2, 0))
                ctk.CTkLabel(score_box, text=f"{val}", font=ctk.CTkFont(size=12, weight="bold"), text_color=color).pack(padx=4, pady=(0, 2))

            # Notes
            notes = idea.get("notes", "")
            if notes:
                ctk.CTkLabel(content, text=f"≡ƒÆí {notes}", font=ctk.CTkFont(size=10), text_color="#6b7280", wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(2, 0))

        self._update_selected_count()

    def _update_selected_count(self):
        """Update the selected count label."""
        count = sum(1 for _, var in self.idea_checkboxes if var.get())
        self.idea_selected_lbl.configure(text=f"─É├ú chß╗ìn: {count}")

    def auto_select_top_n(self, n):
        """Chß╗ìn top N angles theo total_score."""
        # Deselect all first
        for _, var in self.idea_checkboxes:
            var.set(False)

        # Sort by total_score, select top N
        sorted_ideas = sorted(self.idea_checkboxes, key=lambda x: x[0].get("total_score", 0), reverse=True)
        for i, (idea, var) in enumerate(sorted_ideas):
            if i < n:
                var.set(True)

        self._update_selected_count()
        self.idea_console.log(f"[+] ─É├ú tß╗▒ ─æß╗Öng chß╗ìn Top {n} angle theo ─æiß╗âm cao nhß║Ñt.")

    def deselect_all_ideas(self):
        """Bß╗Å chß╗ìn tß║Ñt cß║ú."""
        for _, var in self.idea_checkboxes:
            var.set(False)
        self._update_selected_count()

    def save_selected_angles_action(self):
        """L╞░u c├íc angle ─æ├ú tick chß╗ìn v├áo selected_angles.json."""
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn dß╗▒ ├ín tr╞░ß╗¢c.")
            return

        selected = [idea for idea, var in self.idea_checkboxes if var.get()]
        if not selected:
            messagebox.showwarning("Ch╞░a chß╗ìn", "Ch╞░a chß╗ìn angle n├áo ─æß╗â l╞░u. Tick chß╗ìn ├¡t nhß║Ñt 1 angle.")
            return

        folders = self.project_manager.get_project_folders(self.active_project_slug)
        path = save_selected_angles(folders["root"], selected)
        self.idea_console.log(f"[+] ─É├ú l╞░u {len(selected)} angle v├áo selected_angles.json")
        messagebox.showinfo("─É├ú l╞░u", f"─É├ú l╞░u {len(selected)} angle ─æ╞░ß╗úc chß╗ìn.\nFile: {path}\n\nSau ─æ├│ v├áo tab Storyboard AI ─æß╗â tß║ío storyboard cho tß╗½ng angle.")

    # ==================== CLIP LIBRARY TAB ====================

    def build_tab_clip_library(self):
        """Tab Kho Ph├┤i ΓÇö quß║ún l├╜ clip library cß╗ºa project."""
        tab = self.tab_flow1.tab("≡ƒôª Kho clip")
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=7)
        tab.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Controls & Stats ---
        left = ctk.CTkScrollableFrame(tab, fg_color="transparent", width=260)
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        ctk.CTkLabel(left, text="≡ƒôª Kho Ph├┤i", font=ctk.CTkFont(size=16, weight="bold"), text_color="#f59e0b").pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(left, text="Quß║ún l├╜, review v├á tag c├íc clip ph├┤i\ncß╗ºa dß╗▒ ├ín hiß╗çn tß║íi", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left").pack(anchor="w", pady=(0, 12))

        # Import buttons
        self.btn_lib_import = ctk.CTkButton(
            left, text="Γ₧ò Import Clips V├áo Kho", command=self.lib_import_clips,
            height=36, fg_color="#f59e0b", hover_color="#d97706",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#000000"
        )
        self.btn_lib_import.pack(fill="x", pady=(4, 4))

        self.btn_lib_open_dir = ctk.CTkButton(
            left, text="≡ƒôü Mß╗ƒ Th╞░ Mß╗Ñc Kho Ph├┤i", command=self.lib_open_dir,
            height=30, **secondary_button_kwargs()
        )
        self.btn_lib_open_dir.pack(fill="x", pady=4)

        ctk.CTkFrame(left, height=1, fg_color="#2d2d34").pack(fill="x", pady=8)

        # Filters
        ctk.CTkLabel(left, text="Lß╗ìc clips:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(4, 4))

        ctk.CTkLabel(left, text="Theo trß║íng th├íi:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.lib_filter_status = ctk.CTkComboBox(
            left,
            values=["Tß║Ñt cß║ú"] + CLIP_STATUSES,
            command=lambda v: self.lib_refresh_cards(),
            state="readonly", height=28
        )
        self.lib_filter_status.pack(fill="x", pady=(2, 6))
        self.lib_filter_status.set("Tß║Ñt cß║ú")

        ctk.CTkLabel(left, text="Theo loß║íi ph├┤i:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.lib_filter_asset = ctk.CTkComboBox(
            left,
            values=["Tß║Ñt cß║ú"] + ASSET_TYPES,
            command=lambda v: self.lib_refresh_cards(),
            state="readonly", height=28
        )
        self.lib_filter_asset.pack(fill="x", pady=(2, 6))
        self.lib_filter_asset.set("Tß║Ñt cß║ú")

        # Search
        ctk.CTkLabel(left, text="T├¼m kiß║┐m (t├¬n / tag):", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.lib_search_var = ctk.StringVar()
        self.lib_search_var.trace_add("write", lambda *a: self.lib_refresh_cards())
        self.lib_search_entry = ctk.CTkEntry(left, textvariable=self.lib_search_var, placeholder_text="Nhß║¡p tß╗½ kh├│a...", height=28)
        self.lib_search_entry.pack(fill="x", pady=(2, 10))

        ctk.CTkFrame(left, height=1, fg_color="#2d2d34").pack(fill="x", pady=6)

        # Stats
        ctk.CTkLabel(left, text="Thß╗æng k├¬ kho ph├┤i:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(4, 4))
        self.lib_stats_lbl = ctk.CTkLabel(left, text="Ch╞░a c├│ clip n├áo", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left")
        self.lib_stats_lbl.pack(anchor="w")

        # Refresh
        ctk.CTkButton(
            left, text="≡ƒöä L├ám mß╗¢i", command=self.lib_refresh_cards,
            height=28, **secondary_button_kwargs()
        ).pack(fill="x", pady=(10, 4))

        # --- Right Panel: Clip Cards ---
        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.lib_cards_frame = ctk.CTkScrollableFrame(right, fg_color="#0f0f11", corner_radius=8)
        self.lib_cards_frame.grid(row=0, column=0, sticky="nsew")
        self.lib_cards_frame.grid_columnconfigure(0, weight=1)

        self.lib_placeholder_lbl = ctk.CTkLabel(
            self.lib_cards_frame,
            text="Kho ph├┤i trß╗æng.\nNhß║Ñn 'Γ₧ò Import Clips V├áo Kho' ─æß╗â th├¬m ph├┤i video.",
            font=ctk.CTkFont(size=13), text_color="#4b5563"
        )
        self.lib_placeholder_lbl.pack(pady=80)

    # --- CLIP LIBRARY ACTIONS ---

    def _ensure_clip_library(self):
        """Khß╗ƒi tß║ío ClipLibrary cho project ─æang active."""
        if not self.active_project_slug:
            return False
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        self.clip_library = ClipLibrary(folders["root"])
        return True

    def lib_import_clips(self):
        """Import nhiß╗üu file video v├áo Kho Ph├┤i."""
        if not self._ensure_clip_library():
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn dß╗▒ ├ín tr╞░ß╗¢c.")
            return

        files = filedialog.askopenfilenames(
            title="Chß╗ìn c├íc file clip ─æß╗â import v├áo Kho Ph├┤i",
            filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All Files", "*.*")]
        )
        if not files:
            return

        added = 0
        for fp in files:
            self.clip_library.add_clip(
                file_path=fp,
                scene_type="broll",
                asset_type="product_specific",
                tags=[],
                status="pending",
                product_id=self.active_project_slug,
            )
            added += 1

        messagebox.showinfo("Import xong", f"─É├ú import {added} clip v├áo Kho Ph├┤i.\nTrß║íng th├íi ban ─æß║ºu: pending\nBß║ín c├│ thß╗â ─æß╗òi trß║íng th├íi v├á th├¬m tag cho tß╗½ng clip.")
        self.lib_refresh_cards()

    def lib_open_dir(self):
        """Mß╗ƒ th╞░ mß╗Ñc clip_library cß╗ºa project."""
        if not self.active_project_slug:
            return
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        lib_dir = os.path.join(folders["root"], "clip_library")
        os.makedirs(lib_dir, exist_ok=True)
        try:
            os.startfile(lib_dir)
        except Exception as e:
            messagebox.showerror("Lß╗ùi", f"Kh├┤ng mß╗ƒ ─æ╞░ß╗úc th╞░ mß╗Ñc: {e}")

    def lib_refresh_cards(self):
        """Refresh danh s├ích clip cards theo filter hiß╗çn tß║íi."""
        if not self._ensure_clip_library():
            return

        status_f = self.lib_filter_status.get()
        asset_f = self.lib_filter_asset.get()
        query = self.lib_search_var.get().strip()

        clips = self.clip_library.search_clips(
            query=query,
            status_filter=None if status_f == "Tß║Ñt cß║ú" else status_f,
            asset_type_filter=None if asset_f == "Tß║Ñt cß║ú" else asset_f,
        )

        # Update stats
        stats = self.clip_library.get_stats()
        stats_text = (
            f"Tß╗òng: {stats['total']} clip | {stats['total_duration']}s\n"
            f"Γ£à Approved: {stats['approved']}\n"
            f"≡ƒƒí Okay: {stats['okay']}\n"
            f"ΓÅ│ Pending: {stats['pending']}\n"
            f"Γ¥î Rejected: {stats['rejected']}\n"
            f"Γ£é∩╕Å Needs Cut: {stats['needs_cut']}"
        )
        self.lib_stats_lbl.configure(text=stats_text)

        # Clear old cards
        for w in self.lib_cards_frame.winfo_children():
            w.destroy()

        if not clips:
            ctk.CTkLabel(
                self.lib_cards_frame,
                text="Kh├┤ng c├│ clip n├áo.\nThß╗¡ ─æß╗òi bß╗Ö lß╗ìc hoß║╖c import clips mß╗¢i.",
                font=ctk.CTkFont(size=12), text_color="#4b5563"
            ).pack(pady=60)
            return

        STATUS_COLOR = {
            "approved": "#10b981",
            "okay": "#f59e0b",
            "pending": "#94a3b8",
            "rejected": "#ef4444",
            "needs_cut": "#8b5cf6",
        }
        STATUS_LABEL = {
            "approved": "Γ£à Approved",
            "okay": "≡ƒƒí Okay",
            "pending": "ΓÅ│ Pending",
            "rejected": "Γ¥î Rejected",
            "needs_cut": "Γ£é∩╕Å Needs Cut",
        }

        for clip in clips:
            card = ctk.CTkFrame(self.lib_cards_frame, fg_color="#1a1a21", corner_radius=8)
            card.pack(fill="x", padx=8, pady=4)
            card.grid_columnconfigure(1, weight=1)

            # Thumbnail
            thumb_col = ctk.CTkFrame(card, fg_color="#111118", corner_radius=6, width=70, height=125)
            thumb_col.grid(row=0, column=0, padx=(10, 8), pady=8, sticky="ns")
            thumb_col.grid_propagate(False)

            thumb_path = clip.get("thumbnail_path", "")
            if thumb_path and os.path.exists(thumb_path):
                try:
                    pil_img = Image.open(thumb_path).resize((70, 125), Image.BILINEAR)
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(70, 125))
                    thumb_lbl = ctk.CTkLabel(thumb_col, image=ctk_img, text="")
                    thumb_lbl.image = ctk_img
                    thumb_lbl.pack(expand=True)
                except Exception:
                    ctk.CTkLabel(thumb_col, text="≡ƒÄ¼", font=ctk.CTkFont(size=24), text_color="#4b5563").pack(expand=True)
            else:
                ctk.CTkLabel(thumb_col, text="≡ƒÄ¼", font=ctk.CTkFont(size=24), text_color="#4b5563").pack(expand=True)

            # Info column
            info_col = ctk.CTkFrame(card, fg_color="transparent")
            info_col.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="nsew")
            info_col.grid_columnconfigure(0, weight=1)

            # Name + status
            name_row = ctk.CTkFrame(info_col, fg_color="transparent")
            name_row.pack(fill="x")
            ctk.CTkLabel(name_row, text=clip.get("file_name", ""), font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(side="left")

            st = clip.get("status", "pending")
            st_color = STATUS_COLOR.get(st, "#94a3b8")
            st_label = STATUS_LABEL.get(st, st)
            ctk.CTkLabel(name_row, text=st_label, font=ctk.CTkFont(size=10), text_color=st_color, fg_color="#111118", corner_radius=4).pack(side="right")

            # Meta
            dur = clip.get("duration", 0)
            w = clip.get("width", 0)
            h = clip.get("height", 0)
            q = clip.get("quality_score", 0)
            ctk.CTkLabel(info_col, text=f"ΓÅ▒ {dur:.1f}s  |  ≡ƒôÉ {w}├ù{h}  |  Γ¡É Q:{q}", font=ctk.CTkFont(size=11), text_color="#94a3b8", anchor="w").pack(fill="x", pady=2)

            # Tags
            tags = clip.get("tags", [])
            tags_text = "  ".join([f"#{t}" for t in tags]) if tags else "Ch╞░a c├│ tag"
            ctk.CTkLabel(info_col, text=tags_text, font=ctk.CTkFont(size=10), text_color="#6b7280", anchor="w").pack(fill="x")

            # Action buttons
            btn_row = ctk.CTkFrame(info_col, fg_color="transparent")
            btn_row.pack(fill="x", pady=(6, 0))

            clip_id = clip["clip_id"]

            for new_status, btn_label, btn_color in [
                ("approved", "Γ£à", "#10b981"),
                ("okay", "≡ƒƒí", "#f59e0b"),
                ("rejected", "Γ¥î", "#ef4444"),
                ("needs_cut", "Γ£é∩╕Å", "#8b5cf6"),
            ]:
                ctk.CTkButton(
                    btn_row, text=btn_label, width=32, height=26,
                    fg_color="#2e2e38", hover_color=btn_color,
                    command=lambda cid=clip_id, ns=new_status: self.lib_update_status(cid, ns)
                ).pack(side="left", padx=(0, 3))

            # Tag input
            tag_entry = ctk.CTkEntry(btn_row, placeholder_text="Th├¬m tag...", height=26, width=100)
            tag_entry.pack(side="left", padx=(8, 3))
            ctk.CTkButton(
                btn_row, text="+ Tag", width=50, height=26,
                **secondary_button_kwargs(),
                command=lambda cid=clip_id, e=tag_entry: self.lib_add_tag(cid, e.get().strip())
            ).pack(side="left")

            # Notes
            notes = clip.get("notes", "")
            if notes:
                ctk.CTkLabel(info_col, text=f"≡ƒô¥ {notes}", font=ctk.CTkFont(size=10), text_color="#6b7280", anchor="w").pack(fill="x", pady=(2, 0))

    def lib_update_status(self, clip_id, new_status):
        """Cß║¡p nhß║¡t status cho clip."""
        if self.clip_library:
            self.clip_library.update_clip(clip_id, status=new_status)
            self.lib_refresh_cards()

    def lib_add_tag(self, clip_id, tag):
        """Th├¬m tag v├áo clip."""
        if not tag or not self.clip_library:
            return
        clip = next((c for c in self.clip_library.get_all_clips() if c["clip_id"] == clip_id), None)
        if clip:
            tags = clip.get("tags", [])
            if tag not in tags:
                tags.append(tag)
                self.clip_library.update_clip(clip_id, tags=tags)
                self.lib_refresh_cards()

    # ==================== PROMPT ENGINE IN STORYBOARD TAB ====================

    def export_prompts_from_storyboard(self):
        """Xuß║Ñt prompts tß╗½ storyboard ─æ├ú tß║ío (3 formats: .md / .txt / .json)."""
        if not hasattr(self, "latest_storyboard_data") or not self.latest_storyboard_data:
            messagebox.showwarning("Ch╞░a c├│ storyboard", "Vui l├▓ng tß║ío Storyboard AI tr╞░ß╗¢c.")
            return
        if not self.active_project_slug:
            messagebox.showwarning("Ch╞░a chß╗ìn dß╗▒ ├ín", "Vui l├▓ng chß╗ìn dß╗▒ ├ín tr╞░ß╗¢c.")
            return

        folders = self.project_manager.get_project_folders(self.active_project_slug)
        meta = self.active_project_meta or {}
        product_name = meta.get("product_name", "")

        self.storyboard_console.log("[*] ─Éang xuß║Ñt prompts pack (3 formats)...")

        def run():
            result = generate_prompts_from_storyboard(
                storyboard_data=self.latest_storyboard_data,
                product_name=product_name,
                output_dir=folders["root"],
            )
            self.after(0, lambda: self.finish_export_prompts(result))

        threading.Thread(target=run, daemon=True).start()

    def finish_export_prompts(self, result):
        """Xß╗¡ l├╜ sau khi xuß║Ñt prompts xong."""
        if "error" in result:
            self.storyboard_console.log(f"[x] Lß╗ùi: {result['error']}")
            messagebox.showerror("Lß╗ùi", result["error"])
            return

        n = result.get("prompts_count", 0)
        prompts_dir = result.get("prompts_dir", "")
        self.storyboard_console.log(f"[+] ─É├ú xuß║Ñt {n} scene prompts!")
        self.storyboard_console.log(f"[+] ≡ƒô¥ MD: {os.path.basename(result.get('md_path', ''))}")
        self.storyboard_console.log(f"[+] ≡ƒôä TXT: {n} files ri├¬ng lß║╗")
        self.storyboard_console.log(f"[+] ≡ƒÆ╛ JSON: {os.path.basename(result.get('json_path', ''))}")
        self.storyboard_console.log(f"[+] Th╞░ mß╗Ñc: {prompts_dir}")

        ans = messagebox.askyesno(
            "Xuß║Ñt th├ánh c├┤ng",
            f"─É├ú xuß║Ñt {n} scene prompts ra 3 formats!\n\n"
            f"ΓÇó prompts_pack.md ΓÇö review tß╗òng hß╗úp\n"
            f"ΓÇó P01_prompt.txt ... P{str(n).zfill(2)}_prompt.txt ΓÇö copy v├áo AI tool\n"
            f"ΓÇó prompts.json ΓÇö quß║ún l├╜ version\n\n"
            f"Mß╗ƒ th╞░ mß╗Ñc prompts?"
        )
        if ans and prompts_dir and os.path.exists(prompts_dir):
            try:
                os.startfile(prompts_dir)
            except Exception:
                pass

    # ==================== KNOWLEDGE HUB (AI LEARNING) ====================

    def build_tab_knowledge_hub(self):
        """Deprecated: functionality merged into build_tab_learn_and_review."""
        pass


    def start_knowledge_learning(self):
        """K├¡ch hoß║ít tiß║┐n tr├¼nh tß║úi v├á ph├ón t├¡ch video YouTube/TikTok."""
        url = self.in_kb_url.get().strip()
        if not url:
            messagebox.showerror("Thiß║┐u th├┤ng tin", "Vui l├▓ng nhß║¡p link video ─æß╗â hß╗ìc hß╗Åi.")
            return

        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a nhß║¡p Gemini API Key. Vui l├▓ng cß║Ñu h├¼nh ß╗ƒ tab Cß║Ñu h├¼nh.")
            return

        category = self.kb_category_combo.get()
        self.btn_kb_learn.configure(state="disabled", text="ΓÅ│ ─Éang hß╗ìc hß╗Åi...")
        self.kb_console.clear()

        def run():
            result = kb.learn_from_url(url, category, log_callback=self.kb_console.log, auto_approve=True, approved_by="gui_user", approval_mode="auto")
            self.after(0, lambda: self.finish_knowledge_learning(result))

        threading.Thread(target=run, daemon=True).start()

    def finish_knowledge_learning(self, result):
        """Xß╗¡ l├╜ kß║┐t quß║ú trß║ú vß╗ü sau khi ho├án th├ánh tiß║┐n tr├¼nh hß╗ìc."""
        self.btn_kb_learn.configure(state="normal", text="≡ƒºá Bß║»t ─Éß║ºu Hß╗ìc Hß╗Åi (AI Learn)")
        
        if "error" in result:
            messagebox.showerror("Lß╗ùi hß╗ìc hß╗Åi", result["error"])
            return

        slug = result.get("slug")
        title = result.get("title", "B├ái hß╗ìc")
        self.in_kb_url.set("")
        self.kb_refresh_list()
        
        # Load details of new learned video
        self.kb_view_item(slug)
        
        # Refresh script dropdown in script tab
        self.script_refresh_learned_dropdown()
        
        messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú hß╗ìc xong video mß║½u:\n'{title}'\n\nBß║ín c├│ thß╗â ├íp dß╗Ñng phong c├ích n├áy trong tab Kß╗ïch bß║ún!")

    def kb_refresh_list(self):
        """Cß║¡p nhß║¡t giao diß╗çn danh s├ích b├ái hß╗ìc ─æ├ú l╞░u."""
        for widget in self.kb_list_scroll.winfo_children():
            widget.destroy()

        learned_list = kb.load_learned_list()
        if not learned_list:
            lbl = ctk.CTkLabel(
                self.kb_list_scroll, 
                text="Ch╞░a c├│ b├ái hß╗ìc n├áo.\nH├úy d├ín link ß╗ƒ cß╗Öt tr├íi ─æß╗â AI hß╗ìc.", 
                font=ctk.CTkFont(size=12),
                text_color="#4b5563"
            )
            lbl.pack(pady=40)
            return

        # Render list in reverse order (newest first)
        for item in reversed(learned_list):
            slug = item.get("slug")
            title = item.get("title", "B├ái hß╗ìc")
            platform = item.get("platform", "YouTube")
            category = item.get("category", "Review")
            date_str = item.get("date_learned", "")

            # Card frame
            card = ctk.CTkFrame(self.kb_list_scroll, fg_color="#1e1e24", corner_radius=8)
            card.pack(fill="x", padx=5, pady=4)
            card.grid_columnconfigure(0, weight=1)

            # Context col
            ctk.CTkLabel(
                card, 
                text=title, 
                font=ctk.CTkFont(size=12, weight="bold"), 
                anchor="w",
                wraplength=200,
                justify="left"
            ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")

            meta_text = f"Nguß╗ôn: {platform}  |  Ph├ón loß║íi: {category}"
            if date_str:
                meta_text += f"  |  {date_str}"

            ctk.CTkLabel(
                card, 
                text=meta_text, 
                font=ctk.CTkFont(size=10), 
                text_color="#94a3b8",
                anchor="w"
            ).grid(row=1, column=0, padx=10, pady=(0, 8), sticky="w")

            # Actions row
            act_row = ctk.CTkFrame(card, fg_color="transparent")
            act_row.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")

            ctk.CTkButton(
                act_row, 
                text="Xem b├ái hß╗ìc", 
                width=80, 
                height=24,
                fg_color="#10b981", 
                hover_color="#059669",
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda s=slug: self.kb_view_item(s)
            ).pack(side="left", padx=(0, 5))

            ctk.CTkButton(
                act_row, 
                text="X├│a", 
                width=50, 
                height=24,
                fg_color="#ef4444", 
                hover_color="#dc2626",
                font=ctk.CTkFont(size=10),
                command=lambda s=slug: self.kb_delete_item(s)
            ).pack(side="left")

    def kb_view_item(self, slug):
        if not hasattr(self, "review_textboxes"):
            return
            
        for tb in self.review_textboxes.values():
            tb.delete("1.0", "end")
            
        if hasattr(self, "lbl_preview_title"):
            self.lbl_preview_title.configure(text="≡ƒôä Chi Tiß║┐t B├ái Hß╗ìc ─É├ú L╞░u")
            self.btn_approve_review.grid_remove()
            self.btn_reject_review.grid_remove()

        from core.knowledge_store import get_store
        entry = get_store().get_entry(slug)
        output_dir = entry.get("job_output_dir") if entry else None
        
        # Try to read directly from md files if they exist
        if output_dir and __import__("os").path.exists(output_dir):
            import os
            def read_md(fname):
                path = os.path.join(output_dir, fname)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read()
                return None
                
            summary = read_md("knowledge_proposal.md") or read_md("learning_proposal.md") or read_md("summary.md")
            analysis = read_md("analysis.md")
            setup = read_md("setup.md")
            prompt = read_md("prompt_mapping.md") or read_md("prompt.md")
            
            if summary: self.review_textboxes["T├│m tß║»t"].insert("1.0", summary)
            else: self.review_textboxes["T├│m tß║»t"].insert("1.0", "(Kh├┤ng c├│ nß╗Öi dung t├│m tß║»t tß╗½ file)")
                
            if analysis: self.review_textboxes["Ph├ón t├¡ch"].insert("1.0", analysis)
            else: self.review_textboxes["Ph├ón t├¡ch"].insert("1.0", "(Kh├┤ng c├│ nß╗Öi dung ph├ón t├¡ch tß╗½ file)")
                
            if setup: self.review_textboxes["Setup"].insert("1.0", setup)
            else: self.review_textboxes["Setup"].insert("1.0", "(Kh├┤ng c├│ nß╗Öi dung setup tß╗½ file)")
                
            if prompt: self.review_textboxes["Prompt"].insert("1.0", prompt)
            else: self.review_textboxes["Prompt"].insert("1.0", "(Kh├┤ng c├│ nß╗Öi dung prompt tß╗½ file)")
            return

        # Fallback to DB entry data
        detail = kb.get_learned_detail(slug)
        if not detail:
            self.review_textboxes["T├│m tß║»t"].insert("1.0", "Kh├┤ng t├¼m thß║Ñy dß╗» liß╗çu chi tiß║┐t cß╗ºa b├ái hß╗ìc n├áy.")
            return
        
        title = detail.get("title", "")
        platform = detail.get("platform", "YouTube")
        transcript = detail.get("transcript", "")
        structure = detail.get("structure", "")
        copywriting = detail.get("copywriting_style", "")
        lessons = detail.get("key_lessons", "")

        summary_md = f"# TI├èU ─Éß╗Ç: {title}\n- Nß╗ün tß║úng: {platform}\n\n## B├ÇI Hß╗îC QUAN TRß╗îNG:\n{lessons}"
        analysis_md = f"## 1. Cß║ñU TR├ÜC Kß╗èCH Bß║óN (HOOK - BODY - CTA):\n{structure}\n\n## 2. PHONG C├üCH H├ÇNH V─éN:\n{copywriting}"
        setup_md = "(Kh├┤ng c├│ dß╗» liß╗çu setup quay dß╗▒ng trong DB)"
        prompt_md = f"## Lß╗£I THOß║áI CHI TIß║╛T (TRANSCRIPT):\n{transcript}"

        self.review_textboxes["T├│m tß║»t"].insert("1.0", summary_md)
        self.review_textboxes["Ph├ón t├¡ch"].insert("1.0", analysis_md)
        self.review_textboxes["Setup"].insert("1.0", setup_md)
        self.review_textboxes["Prompt"].insert("1.0", prompt_md)

    def kb_delete_item(self, slug):
        """X├│a b├ái hß╗ìc khß╗Åi kho dß╗» liß╗çu."""
        detail = kb.get_learned_detail(slug)
        title = detail.get("title", "B├ái hß╗ìc") if detail else "B├ái hß╗ìc n├áy"
        
        ans = messagebox.askyesno("X├íc nhß║¡n x├│a", f"Bß║ín c├│ chß║»c chß║»n muß╗æn x├│a b├ái hß╗ìc:\n'{title}'\nkhß╗Åi Kho tri thß╗⌐c kh├┤ng?")
        if ans:
            kb.delete_learned_item(slug)
            self.kb_refresh_list()
            
            # Clear textboxes
            for tb in self.review_textboxes.values():
                tb.delete("1.0", "end")
            self.review_textboxes["T├│m tß║»t"].insert("1.0", "─É├ú x├│a b├ái hß╗ìc th├ánh c├┤ng.")
            
            # Refresh script dropdown in script tab
            self.script_refresh_learned_dropdown()

    # --- ENVIRONMENT CHECKS ---
    
    def _run_all_checks(self):
        """Run all system checks at once."""
        self.check_ffmpeg()
        self.check_gemini()
        self.check_ytdlp()

    def check_ffmpeg(self):
        """Verifies if FFmpeg is configured or available in system PATH."""
        ffmpeg_bin = config.FFMPEG_PATH if config.FFMPEG_PATH else "ffmpeg"
        import subprocess
        try:
            res = subprocess.run([ffmpeg_bin, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                self.ffmpeg_ind.set_ok()
                return True
        except Exception:
            pass
        self.ffmpeg_ind.set_error()
        return False

    def check_ytdlp(self):
        """Checks if the yt-dlp library can import and run."""
        try:
            import yt_dlp
            self.ytdlp_ind.set_ok()
            return True
        except ImportError:
            self.ytdlp_ind.set_error()
            return False

    def check_gemini_silent(self):
        """Performs a silent check on startup."""
        if config.GEMINI_API_KEY and config.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            self.gemini_ind.set_info("─É├â Cß║ñU H├îNH KEY")
        else:
            self.gemini_ind.set_error("CH╞»A C├ô KEY")

    def check_gemini(self):
        """Actively checks if the Gemini API Key is working by hitting the endpoint."""
        api_key = config.GEMINI_API_KEY
        if not api_key:
            self.gemini_ind.set_error("THIß║╛U KEY API")
            messagebox.showerror("Lß╗ùi Cß║Ñu H├¼nh", "Gemini API Key trß╗æng. Vui l├▓ng nhß║¡p kh├│a API ß╗ƒ tab Cß║Ñu h├¼nh.")
            return False
            
        self.gemini_ind.set_info("─ÉANG Gß╗¼I THß╗¼...")
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": "Say OK"}]}]}
        try:
            r = requests.post(url, json=payload, timeout=8)
            if r.status_code == 200:
                self.gemini_ind.set_ok("Kß║╛T Nß╗ÉI OK")
                messagebox.showinfo("Kiß╗âm tra th├ánh c├┤ng", "─É├ú kß║┐t nß╗æi th├ánh c├┤ng vß╗¢i Google Gemini API!")
                return True
            else:
                self.gemini_ind.set_error("Lß╗ûI API KEY")
                messagebox.showerror("Lß╗ùi Gemini API", f"M├ú lß╗ùi HTTP {r.status_code}: {r.text}")
        except Exception as e:
            self.gemini_ind.set_error("Lß╗ûI Kß║╛T Nß╗ÉI")
            messagebox.showerror("Lß╗ùi Kß║┐t Nß╗æi", f"Kh├┤ng thß╗â kß║┐t nß╗æi ─æß║┐n Gemini API: {e}")
        return False

    # --- PROJECT FLOW ACTIONS ---
    
    def load_project_list(self):
        """Scans folder and reloads the project combobox dropdown."""
        projects = self.project_manager.list_projects()
        if not projects:
            self.proj_combobox.configure(values=["Ch╞░a c├│ dß╗▒ ├ín"])
            self.proj_combobox.set("Ch╞░a c├│ dß╗▒ ├ín")
        else:
            names = [p['name'] for p in projects]
            self.proj_combobox.configure(values=names)
            
            # If we just added a project, keep it active
            if self.active_project_slug:
                meta = self.project_manager.get_metadata(self.active_project_slug)
                if meta:
                    self.proj_combobox.set(meta.get('product_name', ''))

    def on_project_combobox_change(self, value):
        """Triggered when user selects a different project from the dropdown list."""
        if value == "Ch╞░a c├│ dß╗▒ ├ín":
            return
            
        projects = self.project_manager.list_projects()
        for p in projects:
            if p['name'] == value:
                self.load_project_details(p['slug'])
                break

    def load_project_details(self, slug):
        """Populates UI elements in all tabs with project configurations from metadata."""
        self.active_project_slug = slug
        meta = self.project_manager.get_metadata(slug)
        self.active_project_meta = meta
        
        if not meta:
            return
            
        # Tab 1 & Storyboard AI Product Info
        product_name_val = meta.get('product_name', '')
        self.in_prod_name.set(product_name_val)
        self.sb_prod_name.set(product_name_val)
        
        desc_val = meta.get('description', '')
        self.in_prod_desc.set(desc_val)
        self.sb_prod_desc.set(desc_val)
        
        self.in_prod_price.set(meta.get('price', ''))
        
        usp_val = meta.get('selling_points', '')
        self.in_prod_usp.set(usp_val)
        self.sb_prod_usp.set(usp_val)
        
        audience_val = meta.get('target_audience', '')
        self.in_prod_audience.set(audience_val)
        self.sb_prod_audience.set(audience_val)
        
        pain_val = meta.get('pain_points', '')
        self.in_prod_pain.set(pain_val)
        self.sb_prod_pain.set(pain_val)
        
        # Tab 2 (Keywords)
        kw = meta.get('keywords', {})
        kw_manual = kw.get('manual', [])
        kw_vi = kw.get('vi', [])
        kw_en = kw.get('en', [])
        kw_zh = kw.get('zh', [])
        search_terms = kw_manual or self._unique_keywords(kw_vi + kw_en + kw_zh)

        self.in_keywords_display.delete("1.0", "end")
        if search_terms:
            self.in_keywords_display.insert("1.0", "\n".join(search_terms))
        
        # Refresh material count
        folders = self.project_manager.get_project_folders(slug)
        mats = list_downloaded_materials(folders["materials"])
        self.lbl_downloaded_count.configure(text=f"Sß╗æ ph├┤i ─æ├ú tß║úi th├ánh c├┤ng: {len(mats)}")
        
        # Tab 3 (Cß║»t clip ph├┤i)
        self.refresh_clip_statistics()
        
        # Tab 4 (Script)
        script_info = meta.get('scripts', {})
        voice_script = script_info.get('voice_script', '')
        if voice_script:
            self.script_display_box.set(voice_script)
            style_name = script_info.get('style', 'Mß╗ƒ ─æß║ºu t├▓ m├▓')
            style_map = {
                "Curiosity hook": "Mß╗ƒ ─æß║ºu t├▓ m├▓",
                "Pain-point hook": "─É├ính thß║│ng nß╗ùi ─æau",
                "Before/after hook": "Tr╞░ß╗¢c v├á sau",
                "Honest review style": "─É├ính gi├í ch├ón thß╗▒c",
                "Cheap but useful style": "Ngon bß╗ò rß║╗",
                "Viral TikTok style": "TikTok Viral (Bß║»t trend)"
            }
            mapped_style = style_map.get(style_name, style_name)
            if mapped_style in SCRIPT_STYLES:
                self.script_style_combo.set(mapped_style)
        else:
            self.script_display_box.set("Ch╞░a sinh kß╗ïch bß║ún. Vui l├▓ng chß╗ìn phong c├ích v├á tß║ío kß╗ïch bß║ún.")
            
        # Tab 5 (Audio)
        audio_info = meta.get('audio', {})
        audio_name = audio_info.get('file_name', '')
        duration = audio_info.get('duration', 0.0)
        
        if audio_name and duration > 0:
            self.lbl_audio_status.configure(text=f"─É├ú nß║íp: {audio_name}", text_color="#10b981")
            self.lbl_audio_duration.configure(text=f"─Éß╗Ö d├ái ├óm thanh thuyß║┐t minh: {duration:.2f} gi├óy")
        else:
            self.lbl_audio_status.configure(text="Ch╞░a nß║íp ├óm thanh (.mp3)", text_color="#ef4444")
            self.lbl_audio_duration.configure(text="─Éß╗Ö d├ái ├óm thanh thuyß║┐t minh: Ch╞░a ─æo")
            
        # Tab 6 (Editor info)
        clips_count = sum(1 for c in meta.get("clips", []) if c.get("status") == "Generated" and not c.get("deleted", False))
        self.lbl_editor_summary.configure(text=f"Th├┤ng tin ph├┤i hiß╗çn c├│:\n- Video ph├┤i gß╗æc: {len(mats)} file\n- Clip ─æ├ú cß║»t dß╗ìc: {clips_count} file\n- Thuyß║┐t minh: {f'{duration:.2f}s ({audio_name})' if duration > 0 else 'Ch╞░a c├│'}")
        
        # Tab 6 (Result)
        export_info = meta.get('exports', {})
        final_video = export_info.get('final_video_path', '')
        if final_video and os.path.exists(final_video):
            self.lbl_video_result_status.configure(text=f"─É├ú dß╗▒ng th├ánh c├┤ng: {os.path.basename(final_video)}\n─É╞░ß╗¥ng dß║½n: {final_video}", text_color="#10b981")
            self.btn_open_export_dir.configure(state="normal")
        else:
            self.lbl_video_result_status.configure(text="Video ch╞░a ─æ╞░ß╗úc dß╗▒ng hoß║╖c file xuß║Ñt ─æ├ú bß╗ï x├│a.", text_color="#e2e8f0")
            self.btn_open_export_dir.configure(state="disabled")
            
        # Caption & Hashtags suggestions
        self.caption_display_box.set(script_info.get('caption', ''))
        self.hashtags_display_box.set(script_info.get('hashtags', ''))

        # Load ideas for Idea Engine tab if exists
        saved_ideas = load_ideas(folders["root"])
        if saved_ideas and saved_ideas.get("ideas"):
            self.current_ideas_data = saved_ideas
            ideas = saved_ideas.get("ideas", [])
            self.idea_stats_lbl.configure(text=f"Tß╗òng: {len(ideas)} angle (─æ├ú l╞░u)")
            self._render_idea_cards(ideas)
        else:
            # Clear ideas display
            for widget in self.idea_cards_frame.winfo_children():
                widget.destroy()
            self.idea_checkboxes.clear()
            ctk.CTkLabel(
                self.idea_cards_frame,
                text="Ch╞░a c├│ ├╜ t╞░ß╗ƒng n├áo.\nNhß║Ñn '≡ƒñû AI Tß║ío ├¥ T╞░ß╗ƒng' ─æß╗â bß║»t ─æß║ºu.",
                font=ctk.CTkFont(size=13), text_color="#4b5563"
            ).pack(pady=60)
            self.idea_stats_lbl.configure(text="Ch╞░a c├│ ├╜ t╞░ß╗ƒng n├áo")

        # Refresh Clip Library for this project
        self._ensure_clip_library()
        if self.clip_library:
            self.lib_refresh_cards()

        # Refresh learned dropdown choices
        self.script_refresh_learned_dropdown()

    def save_project(self):
        """Saves current input product details to create or update a project folder."""
        prod_name = self.in_prod_name.get().strip()
        if not prod_name:
            messagebox.showerror("Thiß║┐u th├┤ng tin", "Vui l├▓ng nhß║¡p t├¬n dß╗▒ ├ín / sß║ún phß║⌐m ─æß╗â tß║ío dß╗▒ ├ín.")
            return
            
        desc = self.in_prod_desc.get().strip()
        price = self.in_prod_price.get().strip()
        usp = self.in_prod_usp.get().strip()
        aud = self.in_prod_audience.get().strip()
        pain = self.in_prod_pain.get().strip()
        
        # Create
        path, slug = self.project_manager.initialize_project(prod_name, desc, price, usp, aud, pain)
        
        # Reload
        self.active_project_slug = slug
        self.load_project_list()
        self.load_project_details(slug)
        messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú khß╗ƒi tß║ío / l╞░u dß╗▒ ├ín th├ánh c├┤ng tß║íi:\nprojects/{slug}")

    # --- ACTION 2: KEYWORDS ---

    def create_quick_project(self, project_name=None):
        if not project_name:
            dialog = ctk.CTkInputDialog(text="Nhß║¡p t├¬n dß╗▒ ├ín / sß║ún phß║⌐m mß╗¢i:", title="Tß║ío dß╗▒ ├ín mß╗¢i")
            project_name = dialog.get_input()
            if not project_name:
                return
            project_name = project_name.strip()
            if not project_name:
                return

        path, slug = self.project_manager.initialize_project(project_name)
        self.active_project_slug = slug
        self.load_project_list()
        self.load_project_details(slug)
        if hasattr(self, "quick_project_name") and self.quick_project_name is not None:
            self.quick_project_name.set("")
        self.switch_flow(1)
        self.tab_flow1.set("≡ƒôï Sß║ún phß║⌐m")
        messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú tß║ío / mß╗ƒ dß╗▒ ├ín:\n{path}")

    def open_auto_pipeline_dialog(self):
        """Mß╗ƒ cß╗¡a sß╗ò nhß║¡p link Shopee/TikTok v├á chß║íy quy tr├¼nh tß╗▒ ─æß╗Öng."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("≡ƒÜÇ Quy Tr├¼nh Tß║ío Dß╗▒ ├ün Tß╗▒ ─Éß╗Öng 1-Click")
        dialog.geometry("600x480")
        dialog.transient(self) # hiß╗ân thß╗ï tr├¬n cß╗¡a sß╗ò cha
        dialog.grab_set() # chiß║┐m quyß╗ün t╞░╞íng t├íc
        
        # Center the dialog window
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Layout
        ctk.CTkLabel(
            dialog,
            text="≡ƒÜÇ Tß╗▒ ─Éß╗Öng H├│a To├án Diß╗çn 1-Click",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#10b981"
        ).pack(pady=(15, 5))
        
        ctk.CTkLabel(
            dialog,
            text="Nhß║¡p link sß║ún phß║⌐m TikTok Video hoß║╖c Shopee Product ─æß╗â AI tß╗▒ ─æß╗Öng\nc├áo th├┤ng tin, tß║úi ph├┤i, cß║»t clip dß╗ìc v├á viß║┐t kß╗ïch bß║ún.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        ).pack(pady=(0, 15))
        
        # URL Entry
        url_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        url_frame.pack(fill="x", padx=25, pady=5)
        
        ctk.CTkLabel(url_frame, text="─É╞░ß╗¥ng dß║½n (URL):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=2)
        in_url = ctk.CTkEntry(url_frame, placeholder_text="D├ín link Shopee hoß║╖c video TikTok v├áo ─æ├óy...", height=35)
        in_url.pack(fill="x")
        
        # Run Button
        btn_run = ctk.CTkButton(
            dialog,
            text="≡ƒÜÇ Bß║»t ─Éß║ºu Quy Tr├¼nh Tß╗▒ ─Éß╗Öng",
            height=38,
            fg_color=COLORS["success"],
            hover_color="#16a34a",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_run.pack(fill="x", padx=25, pady=15)
        
        # Console Log area
        ctk.CTkLabel(dialog, text="Tiß║┐n tr├¼nh ─æang chß║íy:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=25, pady=(5, 2))
        log_box = ConsoleView(dialog, height=200)
        log_box.pack(fill="both", expand=True, padx=25, pady=(0, 15))
        
        def start_run():
            url = in_url.get().strip()
            if not url:
                messagebox.showerror("Thiß║┐u ─æ╞░ß╗¥ng dß║½n", "Vui l├▓ng d├ín link Shopee hoß║╖c TikTok tr╞░ß╗¢c.")
                return
                
            if not config.GEMINI_API_KEY:
                messagebox.showerror("Lß╗ùi cß║Ñu h├¼nh", "Ch╞░a cß║Ñu h├¼nh GEMINI_API_KEY ß╗ƒ tab Cß║Ñu h├¼nh.")
                return
                
            btn_run.configure(state="disabled", text="ΓÅ│ ─Éang chß║íy tß╗▒ ─æß╗Öng...")
            in_url.configure(state="disabled")
            
            def run_thread():
                try:
                    def gui_log(msg):
                        dialog.after(0, lambda: log_box.log(msg))
                        
                    result = pc.run_auto_pipeline(url, log_callback=gui_log)
                    dialog.after(0, lambda: finish_run(result))
                except Exception as ex:
                    dialog.after(0, lambda: log_box.log(f"[x] Lß╗ùi nghi├¬m trß╗ìng: {ex}"))
                    dialog.after(0, lambda: btn_run.configure(state="normal", text="≡ƒÜÇ Chß║íy Lß║íi Quy Tr├¼nh"))
                    
            threading.Thread(target=run_thread, daemon=True).start()
            
        def finish_run(result):
            btn_run.configure(state="normal", text="≡ƒÜÇ Bß║»t ─Éß║ºu Quy Tr├¼nh Tß╗▒ ─Éß╗Öng")
            in_url.configure(state="normal")
            
            slug = result.get("project_slug") or result.get("slug")
            if slug:
                self.active_project_slug = slug
                self.load_project_list()
                self.load_project_details(slug)

            if "error" in result:
                log_box.log("\n" + "="*50)
                log_box.log(f"[x] ≡ƒ¢æ Cß║óNH B├üO: QUY TR├îNH Dß╗¬NG Lß║áI DO Lß╗ûI THIß║╛U T├ÇI NGUY├èN PH├öI")
                log_box.log(f"[x] {result['error']}")
                log_box.log("[*] Dß╗▒ ├ín ─æ├ú ─æ╞░ß╗úc tß║ío sß║╡n. Bß║ín c├│ thß╗â tß╗▒ d├ín ß║únh/video sß║ún phß║⌐m thß╗º c├┤ng v├áo th╞░ mß╗Ñc Phoi/ rß╗ôi bß║Ñm cß║»t clip.")
                log_box.log("="*50)
                btn_run.configure(state="normal", text="≡ƒöä Thß╗¡ Lß║íi Quy Tr├¼nh Tß╗▒ ─Éß╗Öng")
                return
                
            prod_name = result.get("product_name", "Dß╗▒ ├ín mß╗¢i")
            messagebox.showinfo(
                "Ho├án th├ánh xuß║Ñt sß║»c",
                f"─É├ú ho├án th├ánh to├án bß╗Ö quy tr├¼nh tß╗▒ ─æß╗Öng cho sß║ún phß║⌐m:\n'{prod_name}'!\n\n"
                f"ΓÇó Dß╗▒ ├ín mß╗¢i ─æ├ú ─æ╞░ß╗úc khß╗ƒi tß║ío v├á k├¡ch hoß║ít.\n"
                f"ΓÇó T├ái nguy├¬n ph├┤i ─æ├ú ─æ╞░ß╗úc c├áo & cß║»t dß╗ìc 9:16.\n"
                f"ΓÇó Kß╗ïch bß║ún quß║úng c├ío mß╗¢i ─æ├ú ─æ╞░ß╗úc sinh xong.\n\n"
                f"B├óy giß╗¥ bß║ín c├│ thß╗â nß║íp audio thuyß║┐t minh ß╗ƒ tab Audio hoß║╖c bß║Ñm dß╗▒ng ß╗ƒ tab Dß╗▒ng video."
            )
            
            # Switch to Editor tab and close dialog
            self.switch_flow(1)
            self.tab_flow1.set("≡ƒÄ¼ Dß╗▒ng video")
            dialog.destroy()
            
        btn_run.configure(command=start_run)

    def _unique_keywords(self, keywords):
        seen = set()
        result = []
        for keyword in keywords:
            keyword = str(keyword).strip()
            if not keyword:
                continue
            key = keyword.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(keyword)
        return result

    def _parse_keyword_text(self, text):
        normalized = text.replace(";", "\n").replace(",", "\n")
        normalized = normalized.replace("Tiß║┐ng Viß╗çt:", "\n").replace("Tiß║┐ng Anh:", "\n").replace("Tiß║┐ng Trung:", "\n")
        return self._unique_keywords(normalized.splitlines())

    def _build_ai_video_prompts(self, search_terms, prompt_count):
        meta = self.active_project_meta or {}
        product_name = meta.get("product_name", "").strip()
        description = meta.get("description", "").strip()
        usp = meta.get("selling_points", "").strip()
        pain_points = meta.get("pain_points", "").strip()
        audience = meta.get("target_audience", "").strip()

        base_context = []
        if product_name:
            base_context.append(f"Product: {product_name}")
        if description:
            base_context.append(f"Description: {description}")
        if usp:
            base_context.append(f"Key selling point: {usp}")
        if pain_points:
            base_context.append(f"Customer pain point: {pain_points}")
        if audience:
            base_context.append(f"Target audience: {audience}")

        context = ". ".join(base_context)
        prompts = []
        for term in search_terms[:prompt_count]:
            prompts.append(
                f"{context}. Scene idea: {term}. "
                "Show the product in use with a hand-held UGC review feel, quick hook in the first second, "
                "clear before-and-after or problem-solution motion, bright clean lighting, close-up product detail."
            )
        return prompts

    def get_manual_keywords_from_ui(self):
        return self._parse_keyword_text(self.in_keywords_display.get("1.0", "end-1c"))

    def sync_manual_keywords_to_metadata(self, save=True):
        if not self.active_project_slug or not self.active_project_meta:
            return []

        manual_keywords = self.get_manual_keywords_from_ui()
        keywords = self.active_project_meta.get("keywords", {})
        keywords["manual"] = manual_keywords
        keywords.setdefault("vi", [])
        keywords.setdefault("en", [])
        keywords.setdefault("zh", [])
        self.active_project_meta["keywords"] = keywords

        if save:
            self.project_manager.save_metadata(self.active_project_slug, self.active_project_meta)
        return manual_keywords
    
    def generate_project_keywords(self):
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn hoß║╖c tß║ío dß╗▒ ├ín tr╞░ß╗¢c khi mß╗ƒ rß╗Öng key.")
            return

        h1_query = self.in_h1_query.get().strip()
        if h1_query:
            # H╞░ß╗¢ng 1: NLP expansion from entry box
            if not config.GEMINI_API_KEY:
                messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a nhß║¡p Gemini API Key. H├úy cß║Ñu h├¼nh ß╗ƒ tab Cß║Ñu h├¼nh.")
                return
            self.btn_gen_kw.configure(state="disabled", text="AI ─æang mß╗ƒ rß╗Öng...")
            def run():
                try:
                    res = nlp_expand_keywords(h1_query)
                    kws = res.get("vi", []) + res.get("en", []) + res.get("zh", [])
                    def update_gui():
                        self.btn_gen_kw.configure(state="normal", text="AI mß╗ƒ rß╗Öng key")
                        self.in_keywords_display.delete("1.0", "end")
                        self.in_keywords_display.insert("1.0", "\n".join(kws))
                        zh_list = res.get("zh", [])
                        if zh_list:
                            self.in_translate_zh_result.set(zh_list[0])
                        # Save keywords to metadata
                        meta = self.active_project_meta
                        keywords = meta.get("keywords", {})
                        keywords["manual"] = kws
                        keywords["vi"] = res.get("vi", [])
                        keywords["en"] = res.get("en", [])
                        keywords["zh"] = zh_list
                        meta["keywords"] = keywords
                        self.project_manager.save_metadata(self.active_project_slug, meta)
                        self.active_project_meta = meta
                        
                        messagebox.showinfo("Th├ánh c├┤ng", f"AI ─æ├ú ph├ón t├¡ch thß╗▒c thß╗â:\n- Sß║ún phß║⌐m: {res.get('entities', {}).get('product', '')}\n- T├¡nh n─âng: {res.get('entities', {}).get('features', '')}\n- M├áu sß║»c: {res.get('entities', {}).get('color', '')}\n\n─É├ú mß╗ƒ rß╗Öng v├á cß║¡p nhß║¡t tß╗½ kh├│a!")
                    self.after(0, update_gui)
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Lß╗ùi API", f"Lß╗ùi mß╗ƒ rß╗Öng tß╗½ kh├│a: {e}"))
                    self.after(0, lambda: self.btn_gen_kw.configure(state="normal", text="AI mß╗ƒ rß╗Öng key"))
            threading.Thread(target=run, daemon=True).start()
        else:
            # Default behavior (manual keywords text list expansion)
            manual_keywords = self.sync_manual_keywords_to_metadata(save=True)
            if not manual_keywords:
                messagebox.showwarning("Thiß║┐u key", "Vui l├▓ng nhß║¡p t├¬n sß║ún phß║⌐m ß╗ƒ ├┤ tr├¬n hoß║╖c ├¡t nhß║Ñt mß╗Öt tß╗½ kh├│a tr╞░ß╗¢c khi d├╣ng AI mß╗ƒ rß╗Öng.")
                return
            if not config.GEMINI_API_KEY:
                messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a nhß║¡p Gemini API Key. H├úy cß║Ñu h├¼nh ß╗ƒ tab Cß║Ñu h├¼nh.")
                return
            self.btn_gen_kw.configure(state="disabled", text="AI ─æang mß╗ƒ rß╗Öng...")
            def run():
                meta = self.active_project_meta
                seed_keywords = ", ".join(manual_keywords)
                kws = generate_keywords(
                    seed_keywords,
                    meta.get('description', ''),
                    meta.get('price', ''),
                    meta.get('selling_points', ''),
                    meta.get('target_audience', ''),
                    meta.get('pain_points', '')
                )
                self.after(0, lambda: self.finish_keywords_generation(kws))
            threading.Thread(target=run, daemon=True).start()

    def finish_keywords_generation(self, kws):
        self.btn_gen_kw.configure(state="normal", text="AI mß╗ƒ rß╗Öng key")
        if "error" in kws:
            messagebox.showerror("Lß╗ùi API", kws["error"])
            return
            
        # Save
        manual_keywords = self.get_manual_keywords_from_ui()
        expanded_keywords = self._unique_keywords(
            manual_keywords + kws.get("vi", []) + kws.get("en", []) + kws.get("zh", [])
        )
        kws["manual"] = expanded_keywords
        self.active_project_meta["keywords"] = kws
        self.project_manager.save_metadata(self.active_project_slug, self.active_project_meta)

        self.in_keywords_display.delete("1.0", "end")
        self.in_keywords_display.insert("1.0", "\n".join(expanded_keywords))
        messagebox.showinfo("Th├ánh c├┤ng", "─É├ú mß╗ƒ rß╗Öng key t├¼m ph├┤i bß║▒ng AI.")

    def run_manual_translation_zh(self):
        manual_keywords = self.sync_manual_keywords_to_metadata(save=True)
        text_to_translate = "\n".join(manual_keywords)
        if not text_to_translate:
            messagebox.showwarning("Trß╗æng", "Vui l├▓ng nhß║¡p key cß║ºn dß╗ïch trong ├┤ key t├¼m ph├┤i.")
            return
            
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a cß║Ñu h├¼nh GEMINI_API_KEY. Vui l├▓ng nhß║¡p kh├│a API ß╗ƒ tab Cß║Ñu h├¼nh.")
            return
            
        self.btn_run_translate_zh.configure(state="disabled", text="─Éang dß╗ïch...")
        self.in_translate_zh_result.set("─Éang dß╗ïch bß║▒ng AI...")
        
        def run():
            from core.keyword_generator import translate_to_zh
            res = translate_to_zh(text_to_translate)
            
            def update_gui():
                self.btn_run_translate_zh.configure(state="normal", text="Dß╗ïch key")
                self.in_translate_zh_result.set(res)
                if not res.startswith("Lß╗ùi"):
                    translated_keywords = self._parse_keyword_text(res)
                    if translated_keywords:
                        merged_keywords = self._unique_keywords(self.get_manual_keywords_from_ui() + translated_keywords)
                        self.in_keywords_display.delete("1.0", "end")
                        self.in_keywords_display.insert("1.0", "\n".join(merged_keywords))
                        keywords = self.active_project_meta.get("keywords", {})
                        keywords["manual"] = merged_keywords
                        keywords["zh"] = self._unique_keywords(keywords.get("zh", []) + translated_keywords)
                        self.active_project_meta["keywords"] = keywords
                        self.project_manager.save_metadata(self.active_project_slug, self.active_project_meta)

                    try:
                        self.clipboard_clear()
                        self.clipboard_append(res)
                    except Exception:
                        pass
                        
            self.after(0, update_gui)
            
        threading.Thread(target=run, daemon=True).start()

    # --- ACTION 2.2: MATERIAL DOWNLOADS ---
    
    def select_feed_file(self):
        file = filedialog.askopenfilename(
            title="Chß╗ìn Supplier Feed File", 
            filetypes=[("CSV Files", "*.csv"), ("JSON Files", "*.json")]
        )
        if file:
            self.supplier_feed_file = file
            self.lbl_feed_status.configure(text=os.path.basename(file), text_color="#10b981")
            
    def _post_process_downloaded_file(self, filepath, folders, log):
        if not filepath or not os.path.exists(filepath):
            return
            
        # 1. Quality Filter
        use_filter = self.cb_filter_quality_var.get() == "on"
        if use_filter:
            passed = apply_quality_filter(filepath, log)
            if not passed:
                return # File has been deleted
                
        # 2. Split Audio/Video
        use_split = self.cb_split_av_var.get() == "on"
        if use_split and filepath.endswith(".mp4"):
            split_audio_video(filepath, folders["audio"], folders["clips"], log)

    def start_downloading_materials(self):
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn hoß║╖c tß║ío dß╗▒ ├ín tr╞░ß╗¢c.")
            return
            
        active_tab = self.material_tabs.get()
        
        # Collect checkboxes
        use_prod_images = self.prov_prod_images_var.get() == "on"
        use_social = self.prov_social_var.get() == "on"
        use_shopee = self.prov_shopee_var.get() == "on"
        use_pexels = self.prov_pexels_var.get() == "on"
        use_pixabay = self.prov_pixabay_var.get() == "on"
        use_urls = self.prov_urls_var.get() == "on"
        use_feed = self.prov_feed_var.get() == "on"
        use_ai_video = self.prov_ai_video_var.get() == "on"
        
        ai_video_provider = self.ai_video_provider_combo.get()
        try:
            ai_video_prompt_count = int(self.ai_video_prompt_count.get().strip() or "3")
            ai_video_clips_per_prompt = int(self.ai_video_clips_per_prompt.get().strip() or "1")
            ai_video_duration = int(self.ai_video_duration.get().strip() or "5")
        except ValueError:
            messagebox.showerror("Lß╗ùi nhß║¡p liß╗çu", "Sß╗æ prompt AI, sß╗æ clip/key v├á thß╗¥i l╞░ß╗úng phß║úi l├á sß╗æ nguy├¬n.")
            return

        if ai_video_prompt_count <= 0 or ai_video_clips_per_prompt <= 0 or ai_video_duration <= 0:
            messagebox.showerror("Lß╗ùi nhß║¡p liß╗çu", "Sß╗æ prompt AI, sß╗æ clip/key v├á thß╗¥i l╞░ß╗úng phß║úi lß╗¢n h╞ín 0.")
            return
        
        cookie_sel = self.browser_cookies_combo.get()
        pasted_text = self.in_urls_paste.get("1.0", "end-1c").strip()
        urls_to_download = [u.strip() for u in pasted_text.split('\n') if u.strip()]
        
        # Verify inputs based on active tab
        h1_query = self.in_h1_query.get().strip()
        h2_url = self.in_h2_url.get().strip()
        
        if active_tab == "H╞░ß╗¢ng 2: URL sß║ún phß║⌐m":
            if not h2_url:
                messagebox.showerror("Lß╗ùi", "Vui l├▓ng nhß║¡p ─æ╞░ß╗¥ng dß║½n URL sß║ún phß║⌐m ß╗ƒ H╞░ß╗¢ng 2.")
                return
        else:
            # H╞░ß╗¢ng 1: check keywords
            manual_search_terms = self.sync_manual_keywords_to_metadata(save=True)
            if not h1_query and not manual_search_terms and not (use_urls and urls_to_download) and not (use_feed and self.supplier_feed_file):
                messagebox.showwarning("Thiß║┐u th├┤ng tin", "Vui l├▓ng nhß║¡p t├¬n sß║ún phß║⌐m hoß║╖c tß╗½ kh├│a t├¼m kiß║┐m ß╗ƒ H╞░ß╗¢ng 1.")
                return
                
        # Disable buttons
        self.btn_run_downloaders.configure(state="disabled", text="─Éang tß║úi ph├┤i...")
        self.downloads_console.clear()
        
        def run():
            log = self.downloads_console.log
            log("[*] Khß╗ƒi ─æß╗Öng tiß║┐n tr├¼nh c├áo v├á tß║úi ph├┤i th├┤ng minh...")
            
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            materials_dir = folders["materials"]
            os.makedirs(materials_dir, exist_ok=True)
            
            search_terms = []
            
            # --- DIRECTION 2: URL Parsing ---
            if active_tab == "H╞░ß╗¢ng 2: URL sß║ún phß║⌐m":
                log(f"\n--- H╞»ß╗ÜNG 2: PH├éN T├ìCH URL Sß║óN PHß║¿M ---")
                log(f"[*] URL ─æ├¡ch: {h2_url}")
                
                shop_id, item_id = parse_shopee_url(h2_url)
                if shop_id and item_id:
                    # Shopee API extraction with browser cookies support
                    details = fetch_shopee_product_details(shop_id, item_id, browser_cookies=cookie_sel, log_callback=log)
                    if details:
                        log(f"[+] Lß║Ñy th├┤ng tin sß║ún phß║⌐m th├ánh c├┤ng: '{details['title']}'")
                        
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            # Direct Image Download (parallelized)
                            if use_prod_images:
                                log("[*] Tß║úi bß╗Ö s╞░u tß║¡p ß║únh sß║ún phß║⌐m gß╗æc Shopee (Song song)...")
                                for i, img_hash in enumerate(details["images"][:4]):
                                    img_url = f"https://down-vn.img.susercontent.com/file/{img_hash}"
                                    target_path = os.path.join(materials_dir, f"shopee_og_img_{item_id}_{i+1}.jpg")
                                    executor.submit(download_direct, img_url, target_path, log)
                                    
                            # Direct Video Download (parallelized)
                            if use_shopee:
                                log("[*] Tß║úi video m├┤ tß║ú gß╗æc Shopee (Song song)...")
                                for i, video in enumerate(details["video_info_list"][:2]):
                                    video_url = video.get("default_format", {}).get("url") or video.get("url") or f"https://cvf.shopee.vn/{video.get('video_id')}"
                                    if video_url:
                                        executor.submit(download_video_clean, video_url, materials_dir, f"shopee_og_vid_{item_id}", cookie_sel, True, 120, log)
                                    
                        # AI keyword extraction from page details
                        log("[*] AI ─æang b├│c t├ích tß╗½ kh├│a cß╗æt l├╡i tß╗½ ti├¬u ─æß╗ü v├á m├┤ tß║ú...")
                        kw_result = extract_keywords_from_product_page(details["title"], details["description"])
                        search_terms = self._unique_keywords(kw_result.get("vi", []) + kw_result.get("en", []) + kw_result.get("zh", []))
                        log(f"[+] Tß╗½ kh├│a cß╗æt l├╡i AI ─æß╗ü xuß║Ñt ─æß╗â c├áo MXH: {', '.join(search_terms)}")
                    else:
                        log("[!] Kh├┤ng thß╗â c├áo chi tiß║┐t Shopee API. Chuyß╗ân sang c├áo HTML dß╗▒ ph├▓ng...")
                        shop_id = None
                
                # Fallback parser for non-Shopee or blocked Shopee API
                if not shop_id:
                    try:
                        headers = {"User-Agent": "Mozilla/5.0"}
                        res = requests.get(h2_url, headers=headers, timeout=15)
                        if res.status_code == 200:
                            title_match = re.search(r'<title>(.*?)</title>', res.text, re.IGNORECASE)
                            title = title_match.group(1).strip() if title_match else "Sß║ún phß║⌐m mß╗¢i"
                            log(f"[+] Lß║Ñy ti├¬u ─æß╗ü trang web: '{title}'")
                            kw_result = extract_keywords_from_product_page(title, "")
                            search_terms = self._unique_keywords(kw_result.get("vi", []) + kw_result.get("en", []) + kw_result.get("zh", []))
                            log(f"[+] Tß╗½ kh├│a AI cß╗æt l├╡i: {', '.join(search_terms)}")
                    except Exception as e:
                        log(f"[x] Lß╗ùi c├áo generic page: {e}")
                        
            # --- DIRECTION 1: Direct Keyword ---
            else:
                log(f"\n--- H╞»ß╗ÜNG 1: T├èN Sß║óN PHß║¿M & Tß╗¬ KH├ôA ---")
                # Auto NLP expansion if keyword textbox is empty
                manual_search_terms = self.sync_manual_keywords_to_metadata(save=True)
                if h1_query and not manual_search_terms:
                    log(f"[*] ├ö Tß╗½ kh├│a trß╗æng. Tß╗▒ ─æß╗Öng chß║íy AI NLP mß╗ƒ rß╗Öng tß╗½ kh├│a cho: '{h1_query}'...")
                    res = nlp_expand_keywords(h1_query)
                    expanded_kws = res.get("vi", []) + res.get("en", []) + res.get("zh", [])
                    # Update textbox and metadata
                    self.in_keywords_display.delete("1.0", "end")
                    self.in_keywords_display.insert("1.0", "\n".join(expanded_kws))
                    
                    zh_list = res.get("zh", [])
                    if zh_list:
                        self.in_translate_zh_result.set(zh_list[0])
                        
                    meta = self.active_project_meta
                    keywords = meta.get("keywords", {})
                    keywords["manual"] = expanded_kws
                    keywords["vi"] = res.get("vi", [])
                    keywords["en"] = res.get("en", [])
                    keywords["zh"] = zh_list
                    meta["keywords"] = keywords
                    self.project_manager.save_metadata(self.active_project_slug, meta)
                    self.active_project_meta = meta
                    
                    search_terms = expanded_kws
                else:
                    keywords = self.active_project_meta.get("keywords", {})
                    kws_manual = keywords.get("manual", [])
                    kws_vi = keywords.get("vi", [])
                    kws_en = keywords.get("en", [])
                    search_terms = self._unique_keywords(manual_search_terms + kws_manual + kws_en + kws_vi)
            
            # --- START SOCIAL MEDIA CRAWLERS ---
            if not search_terms:
                log("[!] Cß║únh b├ío: Kh├┤ng c├│ tß╗½ kh├│a t├¼m kiß║┐m. Bß╗Å qua c├áo t├¼m kiß║┐m.")
            else:
                log(f"\n[*] Danh s├ích tß╗½ kh├│a t├¼m kiß║┐m: {search_terms[:5]}")
                
                from concurrent.futures import ThreadPoolExecutor
                futures = []
                
                with ThreadPoolExecutor(max_workers=3) as executor:
                    # 1. Product HD Image Search (Google/Shopee query search)
                    if use_prod_images and active_tab == "H╞░ß╗¢ng 1: T├¬n sß║ún phß║⌐m":
                        log("\n--- Bß║«T ─Éß║ªU Tß║óI ß║óNH Sß║óN PHß║¿M HD (Google & Shopee Search) (Song song) ---")
                        for term in search_terms[:2]:
                            futures.append(executor.submit(search_and_download_product_images, term, materials_dir, 4, log))
                            
                    # 2. Shopee Search Crawler
                    if use_shopee and active_tab == "H╞░ß╗¢ng 1: T├¬n sß║ún phß║⌐m":
                        log("\n--- Bß║«T ─Éß║ªU C├ÇO VIDEO T├îM KIß║╛M SHOPEE (Song song) ---")
                        for term in search_terms[:2]:
                            futures.append(executor.submit(
                                search_and_download_shopee, term, materials_dir, 3, False, True, cookie_sel, log
                            ))

                    # 3. DuckDuckGo Scrape for TikTok & Douyin
                    if use_social:
                        log("\n--- Bß║«T ─Éß║ªU C├ÇO T├îM KIß║╛M TIKTOK & DOUYIN (DuckDuckGo Scrape) (Song song) ---")
                        for term in search_terms[:2]:
                            # A. TikTok
                            def crawl_tiktok(t=term):
                                log(f"[*] T├¼m video review tr├¬n TikTok cho: '{t}'...")
                                tiktok_links = search_duckduckgo_urls(t, "tiktok.com", limit=2, log_callback=log)
                                for link in tiktok_links:
                                    download_video_clean(link, materials_dir, prefix="social_tiktok", browser_cookies=cookie_sel, log_callback=log)
                            
                            # B. Douyin
                            def crawl_douyin(t=term):
                                log(f"[*] T├¼m video review tr├¬n Douyin cho: '{t}'...")
                                douyin_links = search_duckduckgo_urls(t, "douyin.com", limit=2, log_callback=log)
                                for link in douyin_links:
                                    download_video_clean(link, materials_dir, prefix="social_douyin", browser_cookies=cookie_sel, log_callback=log)
                                    
                            futures.append(executor.submit(crawl_tiktok))
                            futures.append(executor.submit(crawl_douyin))
                            
                        # 4. Fallback/Standard Social Crawler (Bilibili / Youtube Shorts via standard yt-dlp search)
                        log("\n--- Bß║«T ─Éß║ªU C├ÇO YT SHORTS & BILIBILI (yt-dlp Search) (Song song) ---")
                        for term in search_terms[:2]:
                            futures.append(executor.submit(
                                search_and_download_social, term, materials_dir, 2, 60, True, cookie_sel, log
                            ))

                    # 5. Pexels Download
                    if use_pexels:
                        if not config.PEXELS_API_KEY:
                            log("[!] Bß╗Å qua Pexels: Ch╞░a cß║Ñu h├¼nh API Key.")
                        else:
                            log("\n--- Bß║«T ─Éß║ªU Tß║óI PEXELS STOCK (Song song) ---")
                            for term in search_terms[:2]:
                                futures.append(executor.submit(search_and_download_pexels, term, materials_dir, 3, log))
                                
                    # 6. Pixabay Download
                    if use_pixabay:
                        if not config.PIXABAY_API_KEY:
                            log("[!] Bß╗Å qua Pixabay: Ch╞░a cß║Ñu h├¼nh API Key.")
                        else:
                            log("\n--- Bß║«T ─Éß║ªU Tß║óI PIXABAY STOCK (Song song) ---")
                            for term in search_terms[:2]:
                                futures.append(executor.submit(search_and_download_pixabay, term, materials_dir, 3, log))

                # Chß╗¥ tß║Ñt cß║ú tiß║┐n tr├¼nh c├áo v├á tß║úi ph├┤i ho├án th├ánh
                for fut in futures:
                    try:
                        fut.result()
                    except Exception as err:
                        log(f"[!] Lß╗ùi trong tiß║┐n tr├¼nh c├áo ph├┤i: {err}")

                            
            # 7. Paste URLs Download
            if use_urls and urls_to_download:
                log("\n--- Bß║«T ─Éß║ªU Tß║óI DANH S├üCH URL Tß╗░ D├üN ---")
                download_url_list(urls_to_download, materials_dir, browser_cookies=cookie_sel, log_callback=log)
                
            # 8. Supplier Feed Download
            if use_feed and self.supplier_feed_file:
                log(f"\n--- Bß║«T ─Éß║ªU Tß║óI FILE FEED: {os.path.basename(self.supplier_feed_file)} ---")
                run_supplier_feed_provider(
                    self.supplier_feed_file, 
                    self.active_project_meta.get("product_name", "product"),
                    materials_dir,
                    keywords_list=search_terms,
                    log_callback=log
                )

            # 9. AI Video Generation
            if use_ai_video:
                log(f"\n--- Bß║«T ─Éß║ªU Tß║áO PH├öI AI VIDEO: {ai_video_provider} ---")
                ai_prompts = self._build_ai_video_prompts(search_terms, ai_video_prompt_count)
                generated = generate_ai_video_materials(
                    ai_video_provider,
                    ai_prompts,
                    materials_dir,
                    clips_per_prompt=ai_video_clips_per_prompt,
                    duration_seconds=ai_video_duration,
                    log_callback=log
                )
                if generated:
                    log(f"[+] ─É├ú tß║úi {len(generated)} video AI v├áo th╞░ mß╗Ñc ph├┤i.")
                else:
                    log("[*] ─É├ú tß║ío kß╗ïch bß║ún prompt pack ─æß╗â d├ín thß╗º c├┤ng.")

            # --- POST-PROCESSING FLOW: OpenCV Filter & Audio/Video Splitting ---
            log("\n--- Bß║«T ─Éß║ªU TIß╗ÇN Xß╗¼ L├¥ & Lß╗îC CHß║ñT L╞»ß╗óNG PH├öI ---")
            video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}
            for f in os.listdir(materials_dir):
                ext = os.path.splitext(f)[1].lower()
                if ext in video_extensions:
                    filepath = os.path.abspath(os.path.join(materials_dir, f))
                    try:
                        self._post_process_downloaded_file(filepath, folders, log)
                    except Exception as e:
                        log(f"[!] Lß╗ùi hß║¡u kß╗│ tß╗çp {f}: {e}")
                        
            log("\n[+] Ho├án th├ánh to├án bß╗Ö l╞░ß╗út c├áo v├á tß║úi ph├┤i th├ánh c├┤ng!")
            self.after(0, self.finish_downloading_materials)
            
        threading.Thread(target=run, daemon=True).start()

    def finish_downloading_materials(self):
        self.btn_run_downloaders.configure(state="normal", text="Bß║»t ─Éß║ºu Tß║úi Ph├┤i")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Ho├án th├ánh", "─É├ú ho├án th├ánh l╞░ß╗út tß║úi ph├┤i video.")

    # --- ACTION 2.3: CLIP CUTTING & ANALYSIS ---

    def start_clip_cutting(self):
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn hoß║╖c tß║ío dß╗▒ ├ín tr╞░ß╗¢c.")
            return
            
        try:
            clip_dur = float(self.in_clip_duration.get().strip())
            skip_start = float(self.in_skip_start.get().strip())
            max_clips = int(self.in_max_clips.get().strip())
        except ValueError:
            messagebox.showerror("Lß╗ùi nhß║¡p liß╗çu", "─Éß╗Ö d├ái clip, bß╗Å qua ─æß║ºu video v├á sß╗æ clip tß╗æi ─æa phß║úi l├á sß╗æ hß╗úp lß╗ç.")
            return
            
        if clip_dur <= 0 or skip_start < 0 or max_clips <= 0:
            messagebox.showerror("Lß╗ùi nhß║¡p liß╗çu", "C├íc th├┤ng sß╗æ cß║Ñu h├¼nh phß║úi lß╗¢n h╞ín 0.")
            return
            
        # Disable button
        self.btn_run_clipper.configure(state="disabled", text="─Éang xß╗¡ l├╜ cß║»t clip...")
        self.clip_cutting_console.clear()
        
        # Checkboxes
        export_vert = self.cb_vertical_crop_var.get() == "on"
        mute_audio = self.cb_mute_clip_var.get() == "on"
        analyze_qual = self.cb_quality_analysis_var.get() == "on"
        reject_bad = self.cb_discard_bad_clips_var.get() == "on"
        
        def run():
            self.clip_cutting_console.log("[*] Khß╗ƒi ─æß╗Öng tiß║┐n tr├¼nh tß╗▒ ─æß╗Öng cß║»t clip ph├┤i dß╗ìc...")
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            
            from editor.clip_cutter import cut_materials_into_clips
            new_clips = cut_materials_into_clips(
                folders["materials"],
                folders["clips"],
                self.active_project_slug,
                clip_duration=clip_dur,
                skip_start_seconds=skip_start,
                max_clips_per_video=max_clips,
                export_vertical=export_vert,
                mute_audio=mute_audio,
                analyze_quality=analyze_qual,
                reject_bad_clips=reject_bad,
                progress_callback=self.clip_cutting_console.log
            )
            
            # Save results back to metadata
            meta = self.project_manager.get_metadata(self.active_project_slug)
            if meta:
                if "clips" not in meta:
                    meta["clips"] = []
                meta["clips"].extend(new_clips)
                self.project_manager.save_metadata(self.active_project_slug, meta)
                
            self.after(0, lambda: self.finish_clip_cutting(len(new_clips)))
            
        threading.Thread(target=run, daemon=True).start()

    def finish_clip_cutting(self, count):
        self.btn_run_clipper.configure(state="normal", text="Bß║»t ─Éß║ºu Cß║»t Clip Ph├┤i")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú ho├án th├ánh cß║»t clip ph├┤i! ─É├ú xß╗¡ l├╜ th├¬m {count} clip.")

    def open_clips_dir(self):
        if not self.active_project_slug:
            return
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        clips_path = folders["clips"]
        if os.path.exists(clips_path):
            try:
                os.startfile(clips_path)
            except Exception as e:
                messagebox.showerror("Lß╗ùi mß╗ƒ th╞░ mß╗Ñc", f"Kh├┤ng mß╗ƒ ─æ╞░ß╗úc th╞░ mß╗Ñc: {e}")

    def refresh_clip_statistics(self):
        if not self.active_project_slug:
            self.lbl_total_clips.configure(text="Tß╗òng clip ─æ├ú tß║ío: 0")
            self.lbl_good_clips.configure(text="Clip tß╗æt (>=70): 0")
            self.lbl_okay_clips.configure(text="Clip tß║ím ß╗òn (>=45): 0")
            self.lbl_rejected_clips.configure(text="Clip bß╗ï loß║íi (<45): 0")
            self.lbl_failed_clips.configure(text="Clip lß╗ùi: 0")
            return
            
        meta = self.project_manager.get_metadata(self.active_project_slug)
        if not meta:
            return
            
        clips = meta.get("clips", [])
        total = len(clips)
        good = sum(1 for c in clips if c.get("recommendation") == "Good" and c.get("status") == "Generated")
        okay = sum(1 for c in clips if c.get("recommendation") == "Okay" and c.get("status") == "Generated")
        rejected = sum(1 for c in clips if c.get("status") == "Rejected")
        failed = sum(1 for c in clips if c.get("status") == "Failed")
        
        self.lbl_total_clips.configure(text=f"Tß╗òng clip ─æ├ú tß║ío: {total}")
        self.lbl_good_clips.configure(text=f"Clip tß╗æt (>=70): {good}")
        self.lbl_okay_clips.configure(text=f"Clip tß║ím ß╗òn (>=45): {okay}")
        self.lbl_rejected_clips.configure(text=f"Clip bß╗ï loß║íi (<45): {rejected}")
        self.lbl_failed_clips.configure(text=f"Clip lß╗ùi: {failed}")

    # --- ACTION 2.4: STORYBOARD AI GENERATION ---

    def start_storyboard_generation(self):
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a cß║Ñu h├¼nh GEMINI_API_KEY. Vui l├▓ng nhß║¡p kh├│a API ß╗ƒ tab Cß║Ñu h├¼nh.")
            return
            
        prod_name = self.sb_prod_name.get().strip()
        if not prod_name:
            messagebox.showerror("Thiß║┐u th├┤ng tin", "Vui l├▓ng nhß║¡p T├¬n sß║ún phß║⌐m ─æß╗â tß║ío Storyboard.")
            return
            
        try:
            duration = int(self.sb_duration.get().strip())
            scenes = int(self.sb_scene_count.get().strip())
        except ValueError:
            messagebox.showerror("Lß╗ùi nhß║¡p liß╗çu", "Thß╗¥i l╞░ß╗úng v├á sß╗æ ph├ón cß║únh phß║úi l├á sß╗æ nguy├¬n hß╗úp lß╗ç.")
            return
            
        if duration <= 0 or scenes <= 0:
            messagebox.showerror("Lß╗ùi nhß║¡p liß╗çu", "Thß╗¥i l╞░ß╗úng v├á sß╗æ ph├ón cß║únh phß║úi lß╗¢n h╞ín 0.")
            return
            
        # Disable button & clear previous state
        self.btn_gen_sb.configure(state="disabled", text="─Éang tß║ío bß║▒ng Gemini...")
        self.storyboard_console.clear()
        
        self.sb_preview_box.configure(state="normal")
        self.sb_preview_box.delete("1.0", "end")
        self.sb_preview_box.configure(state="disabled")
        
        self.latest_storyboard_data = None
        
        # Read fields
        desc = self.sb_prod_desc.get().strip()
        usp = self.sb_prod_usp.get().strip()
        pain = self.sb_prod_pain.get().strip()
        aud = self.sb_prod_audience.get().strip()
        style = self.sb_video_style.get().strip()
        bg = self.sb_background.get().strip()
        img_note = self.sb_product_image_note.get().strip()
        bg_note = self.sb_background_image_note.get().strip()
        target = self.sb_prompt_target.get()
        
        def run():
            self.storyboard_console.log("[*] ─Éang gß╗¡i y├¬u cß║ºu sinh ph├ón cß║únh (Storyboard AI) ─æß║┐n Gemini...")
            
            from core.storyboard_generator import generate_storyboard
            res = generate_storyboard(
                prod_name, desc, usp, aud, pain,
                style, bg, img_note, bg_note,
                duration_seconds=duration,
                scene_count=scenes,
                prompt_target=target
            )
            
            self.after(0, lambda: self.finish_storyboard_generation(res))
            
        threading.Thread(target=run, daemon=True).start()

    def finish_storyboard_generation(self, result):
        self.btn_gen_sb.configure(state="normal", text="Tß║ío storyboard")
        
        if "error" in result:
            self.storyboard_console.log(f"[x] Lß╗ùi: {result['error']}")
            messagebox.showerror("Lß╗ùi API", result["error"])
            return
            
        self.latest_storyboard_data = result
        self.storyboard_console.log("[+] Tß║ío Storyboard AI th├ánh c├┤ng!")
        
        # Format and display in preview text box
        title = result.get("title", "Storyboard AI")
        concept = result.get("concept_summary", "")
        dur = result.get("video_duration", 24)
        sc = result.get("scene_count", 6)
        hooks = result.get("hook_options", [])
        ctas = result.get("cta_options", [])
        
        md = f"# Storyboard AI: {title}\n\n"
        md += f"## Tß╗òng quan ├╜ t╞░ß╗ƒng\n{concept}\n"
        md += f"- **Thß╗¥i l╞░ß╗úng**: {dur} gi├óy | **Sß╗æ ph├ón cß║únh**: {sc} cß║únh\n\n"
        
        md += "## Hook ─æß╗ü xuß║Ñt\n"
        for idx, h in enumerate(hooks):
            md += f"{idx + 1}. {h}\n"
        md += "\n"
        
        md += "## CTA ─æß╗ü xuß║Ñt\n"
        for idx, c in enumerate(ctas):
            md += f"{idx + 1}. {c}\n"
        md += "\n"
        
        md += "## Ph├ón cß║únh chi tiß║┐t\n\n"
        for s in result.get("scenes", []):
            md += f"### Scene {s.get('scene_number', 1)} | {s.get('time_range', '')} | {s.get('scene_purpose', '')}\n"
            md += f"* **M├┤ tß║ú h├¼nh ß║únh**: {s.get('visual_description', '')}\n"
            md += f"* **H├ánh ─æß╗Öng**: {s.get('action_description', '')}\n"
            md += f"* **G├│c m├íy/Chuyß╗ân ─æß╗Öng**: {s.get('camera_angle', '')} | {s.get('camera_movement', '')}\n"
            md += f"* **├ünh s├íng/Background**: {s.get('lighting', '')} | {s.get('background', '')}\n"
            md += f"* **Ti├¬u ─æiß╗âm sß║ún phß║⌐m**: {s.get('product_focus', '')}\n"
            md += f"* **Voice**: {s.get('voiceover_line', '')}\n"
            md += f"* **Text**: {s.get('on_screen_text', '')}\n"
            md += f"* **Prompt ß║únh EN**: {s.get('image_prompt_en', '')}\n"
            md += f"* **Prompt video EN**: {s.get('video_prompt_en', '')}\n\n"
            
        self.sb_preview_box.configure(state="normal")
        self.sb_preview_box.delete("1.0", "end")
        self.sb_preview_box.insert("end", md)
        self.sb_preview_box.configure(state="disabled")

    def save_storyboard(self):
        mode = self.sb_mode_combo.get()
        from core.file_manager import to_slug
        
        if mode == "Tr├¡ch xuß║Ñt tß╗½ video mß║½u":
            if not hasattr(self, "latest_extracted_prompt_data") or not self.latest_extracted_prompt_data:
                messagebox.showerror("Trß╗æng", "Vui l├▓ng tr├¡ch xuß║Ñt prompt tß╗½ video th├ánh c├┤ng tr╞░ß╗¢c khi l╞░u.")
                return
                
            video_path = self.sb_sample_video_path.get().strip()
            if not video_path:
                messagebox.showerror("Lß╗ùi", "─É╞░ß╗¥ng dß║½n video trß╗æng.")
                return
                
            video_name = os.path.basename(video_path)
            video_basename = os.path.splitext(video_name)[0]
            
            if self.active_project_slug:
                folders = self.project_manager.get_project_folders(self.active_project_slug)
                output_dir = os.path.join(folders["root"], "storyboard")
                proj_info = f"dß╗▒ ├ín: {self.active_project_slug}"
            else:
                slug = to_slug(self.sb_prod_name.get() or "video_prompt")
                output_dir = os.path.abspath(os.path.join(self.project_manager.get_projects_root(), "..", "storyboard_reports", slug))
                proj_info = f"b├ío c├ío ngo├ái: {slug}"
                
            try:
                os.makedirs(output_dir, exist_ok=True)
                output_file = os.path.join(output_dir, f"{video_basename}_prompt.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(self.latest_extracted_prompt_data)
                
                self.storyboard_console.log(f"[+] ─É├ú l╞░u prompt tr├¡ch xuß║Ñt th├ánh c├┤ng ({proj_info}) tß║íi: {output_file}")
                messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú l╞░u th├ánh c├┤ng tß╗çp prompt tß║íi:\n{output_file}")
            except Exception as e:
                self.storyboard_console.log(f"[x] Lß╗ùi l╞░u Prompt: {e}")
                messagebox.showerror("Lß╗ùi l╞░u file", f"Kh├┤ng thß╗â l╞░u tß╗çp prompt: {e}")
            return
            
        if not hasattr(self, "latest_storyboard_data") or not self.latest_storyboard_data:
            messagebox.showerror("Trß╗æng", "Vui l├▓ng tß║ío Storyboard th├ánh c├┤ng tr╞░ß╗¢c khi l╞░u.")
            return
            
        from core.storyboard_writer import save_storyboard_outputs
        
        if self.active_project_slug:
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            output_dir = os.path.join(folders["root"], "storyboard")
            proj_info = f"dß╗▒ ├ín: {self.active_project_slug}"
        else:
            slug = to_slug(self.sb_prod_name.get())
            output_dir = os.path.abspath(os.path.join(self.project_manager.get_projects_root(), "..", "storyboard_reports", slug))
            proj_info = f"b├ío c├ío ngo├ái: {slug}"
            
        try:
            paths = save_storyboard_outputs(self.latest_storyboard_data, output_dir)
            self.storyboard_console.log(f"[+] ─É├ú l╞░u Storyboard th├ánh c├┤ng ({proj_info}) tß║íi: {output_dir}")
            messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú l╞░u th├ánh c├┤ng 4 file (storyboard.md, storyboard.json, image_prompts.txt, video_prompts.txt) tß║íi:\n{output_dir}")
        except Exception as e:
            self.storyboard_console.log(f"[x] Lß╗ùi l╞░u Storyboard: {e}")
            messagebox.showerror("Lß╗ùi l╞░u file", f"Kh├┤ng thß╗â l╞░u c├íc tß╗çp storyboard: {e}")

    def open_storyboard_dir(self):
        from core.file_manager import to_slug
        mode = self.sb_mode_combo.get()
        
        if self.active_project_slug:
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            output_dir = os.path.join(folders["root"], "storyboard")
        else:
            if mode == "Tr├¡ch xuß║Ñt tß╗½ video mß║½u":
                slug = to_slug(self.sb_prod_name.get() or "video_prompt")
            else:
                slug = to_slug(self.sb_prod_name.get())
            output_dir = os.path.abspath(os.path.join(self.project_manager.get_projects_root(), "..", "storyboard_reports", slug))
            
        if os.path.exists(output_dir):
            try:
                os.startfile(output_dir)
            except Exception as e:
                messagebox.showerror("Lß╗ùi mß╗ƒ th╞░ mß╗Ñc", f"Kh├┤ng mß╗ƒ ─æ╞░ß╗úc th╞░ mß╗Ñc: {e}")
        else:
            messagebox.showwarning("Kh├┤ng tß╗ôn tß║íi", "Th╞░ mß╗Ñc ch╞░a ─æ╞░ß╗úc khß╗ƒi tß║ío. Vui l├▓ng bß║Ñm l╞░u kß║┐t quß║ú tr╞░ß╗¢c.")

    def copy_all_storyboard(self):
        text = self.sb_preview_box.get("1.0", "end-1c").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copy", "─É├ú copy to├án bß╗Ö kß╗ïch bß║ún ph├ón cß║únh (Markdown) v├áo Clipboard!")
        else:
            messagebox.showwarning("Trß╗æng", "Kh├┤ng c├│ kß╗ïch bß║ún ─æß╗â copy.")

    def copy_image_prompts(self):
        if not hasattr(self, "latest_storyboard_data") or not self.latest_storyboard_data:
            messagebox.showwarning("Trß╗æng", "Ch╞░a c├│ dß╗» liß╗çu storyboard ─æß╗â copy.")
            return
            
        prompts = []
        for s in self.latest_storyboard_data.get("scenes", []):
            num = s.get("scene_number", 1)
            en_prompt = s.get("image_prompt_en", "")
            neg_prompt = s.get("negative_prompt", "")
            prompts.append(f"--- SCENE {num} IMAGE PROMPT ---\n{en_prompt}\nNegative Prompt: {neg_prompt}")
            
        text = "\n\n".join(prompts)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copy", "─É├ú copy danh s├ích prompt h├¼nh ß║únh tiß║┐ng Anh v├áo Clipboard!")

    def copy_video_prompts(self):
        if not hasattr(self, "latest_storyboard_data") or not self.latest_storyboard_data:
            messagebox.showwarning("Trß╗æng", "Ch╞░a c├│ dß╗» liß╗çu storyboard ─æß╗â copy.")
            return
            
        prompts = []
        for s in self.latest_storyboard_data.get("scenes", []):
            num = s.get("scene_number", 1)
            en_prompt = s.get("video_prompt_en", "")
            neg_prompt = s.get("negative_prompt", "")
            prompts.append(f"--- SCENE {num} VIDEO PROMPT ---\n{en_prompt}\nNegative Prompt: {neg_prompt}")
            
        text = "\n\n".join(prompts)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copy", "─É├ú copy danh s├ích prompt video tiß║┐ng Anh v├áo Clipboard!")

    def on_sb_mode_changed(self, choice):
        if choice == "Tß║ío tß╗½ v─ân bß║ún (Text)":
            self.sb_video_mode_frame.pack_forget()
            self.sb_text_mode_frame.pack(fill="x", expand=True)
            self.btn_extract_prompt.pack_forget()
            self.btn_gen_sb.pack(side="left", padx=4)
            self.btn_copy_img_p.configure(state="normal")
            self.btn_copy_vid_p.configure(state="normal")
        else:
            self.sb_text_mode_frame.pack_forget()
            self.sb_video_mode_frame.pack(fill="x", expand=True)
            self.btn_gen_sb.pack_forget()
            self.btn_extract_prompt.pack(side="left", padx=4)
            self.btn_copy_img_p.configure(state="disabled")
            self.btn_copy_vid_p.configure(state="disabled")

    def browse_sample_video(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Chß╗ìn video mß║½u ─æß╗â ph├ón t├¡ch",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All files", "*.*")]
        )
        if path:
            self.sb_sample_video_path.set(path)

    def start_prompt_extraction(self):
        offline_only = self.sb_offline_only.get()
        custom_action = self.sb_custom_action.get().strip()
        
        if not offline_only:
            api_key = getattr(config, "GEMINI_API_KEY", "")
            if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a cß║Ñu h├¼nh GEMINI_API_KEY. Vui l├▓ng nhß║¡p kh├│a API ß╗ƒ tab Cß║Ñu h├¼nh.")
                return
            
        video_path = self.sb_sample_video_path.get().strip()
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn tß╗çp video mß║½u hß╗úp lß╗ç tr╞░ß╗¢c khi ph├ón t├¡ch.")
            return
            
        self.btn_extract_prompt.configure(state="disabled", text="─Éang ph├ón t├¡ch...")
        self.storyboard_console.clear()
        
        self.sb_preview_box.configure(state="normal")
        self.sb_preview_box.delete("1.0", "end")
        self.sb_preview_box.configure(state="disabled")
        
        self.latest_extracted_prompt_data = None
        target = self.sb_video_prompt_target.get()
        
        def run():
            if offline_only:
                self.storyboard_console.log(f"[*] Bß║»t ─æß║ºu ph├ón t├¡ch ngoß║íi tuyß║┐n video mß║½u...")
            else:
                self.storyboard_console.log(f"[*] Bß║»t ─æß║ºu tß║úi video mß║½u l├¬n Gemini API...")
            from tools.video_analyser import analyze_video
            
            prompt_text = f"""
Bß║ín l├á mß╗Öt chuy├¬n gia h├áng ─æß║ºu vß╗ü AI Video Prompt Engineering.
H├úy xem kß╗╣ video ─æ╞░ß╗úc tß║úi l├¬n ß╗ƒ tr├¬n, ph├ón t├¡ch chi tiß║┐t v├á viß║┐t b├ío c├ío bß║▒ng tiß║┐ng Viß╗çt:

1. **PH├éN T├ìCH CHI TIß║╛T VIDEO Mß║¬U**:
   - **H├ánh ─æß╗Öng & Diß╗àn tiß║┐n (Action & Motion)**: M├┤ tß║ú chi tiß║┐t h├ánh ─æß╗Öng cß╗ºa tay, ng╞░ß╗¥i hoß║╖c vß║¡t thß╗â trong video.
   - **M├┤i tr╞░ß╗¥ng & Ngß╗» cß║únh (Environment & Context)**: M├┤ tß║ú bß╗æi cß║únh, ph├┤ng nß╗ün, c├íc vß║¡t thß╗â xung quanh, m├áu sß║»c chß╗º ─æß║ío.
   - **├ünh s├íng (Lighting)**: M├┤ tß║ú loß║íi ├ính s├íng (soft, studio, bright sunlight, cinematic...) v├á h╞░ß╗¢ng s├íng.
   - **G├│c m├íy & Chuyß╗ân ─æß╗Öng Camera (Camera work)**: M├┤ tß║ú ti├¬u cß╗▒ (close-up, medium, macro...), g├│c m├íy (top-down, eye-level...) v├á chuyß╗ân ─æß╗Öng (panning, zoom in, static...).
   - **Nhß╗ïp ─æß╗Ö & Thß╗¥i l╞░ß╗úng (Pacing)**: T├│m tß║»t nhß╗ïp ─æß╗Ö chuyß╗ân cß║únh v├á tß╗æc ─æß╗Ö diß╗àn tiß║┐n.

2. **PROMPT RE-CREATION (D├╣ng ─æß╗â sinh video t╞░╞íng tß╗▒)**:
   - Viß║┐t mß╗Öt **Video Prompt bß║▒ng tiß║┐ng Anh** chi tiß║┐t v├á chuy├¬n nghiß╗çp nhß║Ñt t╞░╞íng th├¡ch tß╗æt vß╗¢i c├┤ng cß╗Ñ '{target}' ─æß╗â ng╞░ß╗¥i d├╣ng sao ch├⌐p trß╗▒c tiß║┐p v├áo c├íc AI Video Generator ─æß╗â tß║ío ra mß╗Öt video c├│ c├╣ng bß╗æi cß║únh, chß║Ñt l╞░ß╗úng v├á h├ánh ─æß╗Öng t╞░╞íng tß╗▒.
   - Prompt tiß║┐ng Anh cß║ºn kß║┐t hß╗úp c├íc tß╗½ kh├│a chuy├¬n nghiß╗çp: "vertical 9:16 aspect ratio", "TikTok review style", "highly realistic", "high detail", "8k resolution".
   - ─Éß╗ïnh dß║íng Prompt:
     ```text
     [Copy-ready English Prompt]
     ```

3. **NEGATIVE PROMPT (Tß╗½ kh├│a loß║íi trß╗½)**:
   - C├íc tß╗½ kh├│a loß║íi trß╗½ lß╗ùi h├¼nh ß║únh: "no watermark, no logo, no distorted hands, no deformed product, no text artifacts, no blurry text, extra fingers, bad anatomy, deformed fingers, low quality, grainy".
"""
            
            def gui_log(msg):
                self.after(0, lambda m=msg: self.storyboard_console.log(m))
                
            res = analyze_video(
                video_path, 
                prompt_text=prompt_text, 
                log_callback=gui_log,
                offline_only=offline_only,
                custom_action=custom_action
            )
            self.after(0, lambda: self.finish_prompt_extraction(res, video_path))
            
        threading.Thread(target=run, daemon=True).start()

    def finish_prompt_extraction(self, result, video_path):
        self.btn_extract_prompt.configure(state="normal", text="Tr├¡ch xuß║Ñt prompt")
        
        if result.startswith("Lß╗ùi"):
            self.storyboard_console.log(f"[x] Lß╗ùi: {result}")
            messagebox.showerror("Lß╗ùi tr├¡ch xuß║Ñt", result)
            return
            
        self.latest_extracted_prompt_data = result
        self.storyboard_console.log("[+] Tr├¡ch xuß║Ñt prompt th├ánh c├┤ng!")
        
        self.sb_preview_box.configure(state="normal")
        self.sb_preview_box.delete("1.0", "end")
        self.sb_preview_box.insert("end", result)
        self.sb_preview_box.configure(state="disabled")
        
        # Auto save if project is active
        if self.active_project_slug:
            self.save_storyboard()

    # --- ACTION 3: SCRIPTS ---
    
    def generate_project_script(self):
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn hoß║╖c l╞░u dß╗▒ ├ín tr╞░ß╗¢c.")
            return
            
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lß╗ùi Gemini", "Ch╞░a nhß║¡p Gemini API Key. H├úy cß║Ñu h├¼nh ß╗ƒ tab Cß║Ñu h├¼nh.")
            return
            
        style = self.script_style_combo.get()
        selected_learned = self.script_learned_combo.get()
        
        # Load reference style if selected
        ref_style = None
        if selected_learned != "Kh├┤ng ├íp dß╗Ñng" and hasattr(self, "kb_slug_mapping"):
            slug = self.kb_slug_mapping.get(selected_learned)
            if slug:
                ref_style = kb.get_learned_detail(slug)
                
        self.btn_gen_script.configure(state="disabled", text="─Éang sinh kß╗ïch bß║ún...")
        
        def run():
            meta = self.active_project_meta
            script_res = generate_script(
                meta.get('product_name', ''),
                meta.get('description', ''),
                meta.get('price', ''),
                meta.get('selling_points', ''),
                meta.get('target_audience', ''),
                meta.get('pain_points', ''),
                style=style,
                reference_style_json=ref_style
            )
            
            if "error" in script_res:
                self.after(0, lambda: self.on_script_error(script_res["error"]))
                return
                
            # Save files
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            save_script_files(folders["scripts"], script_res)
            
            # Save metadata
            meta["scripts"] = {
                "style": style,
                "voice_script": script_res["voice_script"],
                "caption": script_res["caption"],
                "hashtags": script_res["hashtags"]
            }
            self.project_manager.save_metadata(self.active_project_slug, meta)
            
            # Reload
            self.after(0, self.finish_script_generation)
            
        threading.Thread(target=run, daemon=True).start()

    def on_script_error(self, err_msg):
        self.btn_gen_script.configure(state="normal", text="Viß║┐t kß╗ïch bß║ún mß╗¢i (AI Gemini)")
        messagebox.showerror("Lß╗ùi sinh kß╗ïch bß║ún", err_msg)

    def finish_script_generation(self):
        self.btn_gen_script.configure(state="normal", text="Viß║┐t kß╗ïch bß║ún mß╗¢i (AI Gemini)")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Th├ánh c├┤ng", "Kß╗ïch bß║ún quß║úng c├ío ─æ├ú ─æ╞░ß╗úc sinh th├ánh c├┤ng!")

    def copy_script_to_clipboard(self):
        script_text = self.script_display_box.get().strip()
        if script_text:
            self.clipboard_clear()
            self.clipboard_append(script_text)
            messagebox.showinfo("Sao ch├⌐p", "─É├ú sao ch├⌐p kß╗ïch bß║ún voiceover v├áo clipboard!")
        else:
            messagebox.showwarning("Trß╗æng", "Kh├┤ng c├│ kß╗ïch bß║ún ─æß╗â sao ch├⌐p.")

    # --- ACTION 4: AUDIO IMPORT ---
    
    def import_voice_audio(self):
        if not self.active_project_slug:
            messagebox.showerror("Lß╗ùi", "Vui l├▓ng chß╗ìn dß╗▒ ├ín tr╞░ß╗¢c.")
            return
            
        file_path = filedialog.askopenfilename(title="Chß╗ìn File Thuyß║┐t Minh ElevenLabs", filetypes=[("Audio files", "*.mp3")])
        if not file_path:
            return
            
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        dest_path = os.path.join(folders["audio"], "voice.mp3")
        
        # Copy file
        import shutil
        try:
            shutil.copy(file_path, dest_path)
            
            # Measure duration
            duration = get_audio_duration(dest_path)
            
            # Update metadata
            meta = self.active_project_meta
            meta["audio"] = {
                "file_name": os.path.basename(file_path),
                "file_path": dest_path,
                "duration": duration
            }
            self.project_manager.save_metadata(self.active_project_slug, meta)
            
            self.load_project_details(self.active_project_slug)
            messagebox.showinfo("Th├ánh c├┤ng", f"─É├ú nß║íp file thuyß║┐t minh. ─Éß╗Ö d├ái ─æo ─æ╞░ß╗úc: {duration:.2f} gi├óy.")
        except Exception as e:
             # ==================== MERGED TAB: Hß╗îC & DUYß╗åT ====================

    def build_tab_learn_and_review(self):
        """Merged tab: Hß╗ìc hß╗Åi tß╗½ video mß║½u + H├áng ─æß╗úi duyß╗çt b├ái hß╗ìc (Bß╗æ cß╗Ñc Tabview cß╗Öt giß╗»a)."""
        tab = self.tab_flow2.tab("≡ƒôÜ Hß╗ìc & Duyß╗çt")
        self._learn_review_tab_instance = LearnReviewTab(tab, self)

    # ==================== MERGED TAB: C├ÇI ─Éß║╢T ====================

    def build_tab_settings_merged(self):
        """Merged tab: Bi├¬n dß╗ïch Prompt + Cß║Ñu h├¼nh hß╗ç thß╗æng."""
        tab = self.tab_flow2.tab("≡ƒ¢á∩╕Å C├ái ─Éß║╖t")
        self._settings_tab_instance = SettingsTab(tab, self)chor="w"
                         ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 2))

        # Gemini API Key
        row_label("≡ƒöæ Gemini API Key:", 0)
        self.sett_gemini_key = ctk.CTkEntry(parent, placeholder_text="Nhß║¡p Gemini API Key...",
                                             height=34, show="ΓÇó", corner_radius=8,
                                             fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                             text_color=COLORS["text"])
        self.sett_gemini_key.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        if getattr(_cfg, "GEMINI_API_KEY", "") and _cfg.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            self.sett_gemini_key.insert(0, _cfg.GEMINI_API_KEY)

        # Pexels API Key
        row_label("≡ƒû╝∩╕Å Pexels API Key:", 2)
        self.sett_pexels_key = ctk.CTkEntry(parent, placeholder_text="Nhß║¡p Pexels API Key...",
                                             height=32, show="ΓÇó", corner_radius=8,
                                             fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                             text_color=COLORS["text"])
        self.sett_pexels_key.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        if getattr(_cfg, "PEXELS_API_KEY", ""):
            self.sett_pexels_key.insert(0, _cfg.PEXELS_API_KEY)

        # Pixabay API Key
        row_label("≡ƒÄ¿ Pixabay API Key:", 4)
        self.sett_pixabay_key = ctk.CTkEntry(parent, placeholder_text="Nhß║¡p Pixabay API Key...",
                                              height=32, show="ΓÇó", corner_radius=8,
                                              fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                              text_color=COLORS["text"])
        self.sett_pixabay_key.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        if getattr(_cfg, "PIXABAY_API_KEY", ""):
            self.sett_pixabay_key.insert(0, _cfg.PIXABAY_API_KEY)

        # FFmpeg path
        row_label("≡ƒÄ¼ ─É╞░ß╗¥ng dß║½n FFmpeg:", 6)
        row_ff = ctk.CTkFrame(parent, fg_color="transparent")
        row_ff.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        row_ff.grid_columnconfigure(0, weight=1)
        self.sett_ffmpeg_path = ctk.CTkEntry(row_ff, placeholder_text="─É╞░ß╗¥ng dß║½n tß╗¢i ffmpeg.exe...",
                                              height=32, corner_radius=8,
                                              fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                              text_color=COLORS["text"])
        self.sett_ffmpeg_path.grid(row=0, column=0, sticky="ew")
        if getattr(_cfg, "FFMPEG_PATH", ""):
            self.sett_ffmpeg_path.insert(0, _cfg.FFMPEG_PATH)
        ctk.CTkButton(row_ff, text="...", width=36, height=32,
                      command=self._browse_ffmpeg, **secondary_button_kwargs()
                      ).grid(row=0, column=1, padx=(6, 0))

        # Projects root
        row_label("≡ƒôü Th╞░ mß╗Ñc gß╗æc Dß╗▒ ├ín:", 8)
        row_pr = ctk.CTkFrame(parent, fg_color="transparent")
        row_pr.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        row_pr.grid_columnconfigure(0, weight=1)
        self.sett_projects_root = ctk.CTkEntry(row_pr, placeholder_text="─É╞░ß╗¥ng dß║½n th╞░ mß╗Ñc gß╗æc dß╗▒ ├ín...",
                                               height=32, corner_radius=8,
                                               fg_color=COLORS["surface_3"], border_color=COLORS["border"],
                                               text_color=COLORS["text"])
        self.sett_projects_root.grid(row=0, column=0, sticky="ew")
        if getattr(_cfg, "PROJECTS_ROOT", ""):
            self.sett_projects_root.insert(0, _cfg.PROJECTS_ROOT)
        ctk.CTkButton(row_pr, text="...", width=36, height=32,
                      command=self._browse_projects_root, **secondary_button_kwargs()
                      ).grid(row=0, column=1, padx=(6, 0))

        # Grok key (needed by save_settings)
        self.sett_grok_key = ctk.CTkEntry(parent, height=0, fg_color="transparent",
                                           border_width=0, text_color=COLORS["text"])
        self.sett_grok_key.grid(row=10, column=0)
        if getattr(_cfg, "GROK_API_KEY", ""):
            self.sett_grok_key.insert(0, _cfg.GROK_API_KEY)

        # Save button
        ctk.CTkButton(parent, text="≡ƒÆ╛ L╞░u Cß║Ñu H├¼nh", command=self.save_settings,
                      height=38, **primary_button_kwargs()
                      ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=16)

        # System check section
        ctk.CTkLabel(parent, text="≡ƒöì Kiß╗âm Tra Hß╗ç Thß╗æng:", font=font(13, "bold"), anchor="w"
                     ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(4, 6))

        self.ffmpeg_ind = StatusIndicator(parent, "FFmpeg")
        self.ffmpeg_ind.grid(row=13, column=0, columnspan=2, sticky="w", pady=3)
        self.gemini_ind = StatusIndicator(parent, "Gemini AI API")
        self.gemini_ind.grid(row=14, column=0, columnspan=2, sticky="w", pady=3)
        self.ytdlp_ind = StatusIndicator(parent, "yt-dlp")
        self.ytdlp_ind.grid(row=15, column=0, columnspan=2, sticky="w", pady=3)

        row_btns = ctk.CTkFrame(parent, fg_color="transparent")
        row_btns.grid(row=16, column=0, columnspan=2, sticky="ew", pady=10)
        ctk.CTkButton(row_btns, text="Γû╢ FFmpeg", command=self.check_ffmpeg, height=28, **secondary_button_kwargs()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_btns, text="Γû╢ Gemini", command=self.check_gemini, height=28, **secondary_button_kwargs()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_btns, text="Γû╢ yt-dlp", command=self.check_ytdlp, height=28, **secondary_button_kwargs()).pack(side="left")


    def _browse_ffmpeg(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(title="Chß╗ìn ffmpeg.exe", filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if path and hasattr(self, "sett_ffmpeg_path"):
            self.sett_ffmpeg_path.delete(0, "end")
            self.sett_ffmpeg_path.insert(0, path)

    def _browse_projects_root(self):
        from tkinter.filedialog import askdirectory
        path = askdirectory(title="Chß╗ìn th╞░ mß╗Ñc gß╗æc dß╗▒ ├ín")
        if path and hasattr(self, "sett_projects_root"):
            self.sett_projects_root.delete(0, "end")
            self.sett_projects_root.insert(0, path)


if __name__ == "__main__":
    # Kiß╗âm tra cß║Ñu h├¼nh v├á cß║únh b├ío nß║┐u thiß║┐u
    config.verify_config()
    app = HermesTikTokVideoFactoryApp()
    app.mainloop()
