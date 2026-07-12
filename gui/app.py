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
from gui.tabs.idea_engine_tab import IdeaEngineTab
from gui.tabs.script_generator_tab import ScriptGeneratorTab
from gui.tabs.audio_generator_tab import AudioGeneratorTab
from gui.tabs.storyboard_tab import StoryboardTab
from gui.tabs.agent_jobs_tab import AgentJobsTab
from gui.tabs.assistant_tab import AssistantTab

class HermesTikTokVideoFactoryApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Settings
        self.title("Hermes TikTok Video Factory 🎬")
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
            text="🚀 Quy Trình Tự Động (Auto)",
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
            text="Kiểm Tra Hệ Thống:", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.check_label.pack(anchor="w", padx=20, pady=(5, 5))
        
        # Indicators
        self.ffmpeg_ind = StatusIndicator(self.sidebar, "1. Bộ giải mã FFmpeg")
        self.ffmpeg_ind.pack(fill="x", padx=20, pady=4)
        
        self.gemini_ind = StatusIndicator(self.sidebar, "2. Gemini AI API")
        self.gemini_ind.pack(fill="x", padx=20, pady=4)
        
        self.ytdlp_ind = StatusIndicator(self.sidebar, "3. Thư viện yt-dlp")
        self.ytdlp_ind.pack(fill="x", padx=20, pady=(4, 12))
        
        # Single compact check button
        self.btn_check_all = ctk.CTkButton(
            self.sidebar, 
            text="🔧 Kiểm Tra Hệ Thống", 
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
            text="🎬 Cắt Ghép Video", 
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            width=180,
            corner_radius=8,
            command=lambda: self.switch_flow(1)
        )
        self.btn_flow1.pack(side="left", padx=(0, 8))

        self.btn_flow2 = ctk.CTkButton(
            flows_container, 
            text="🧠 AI Phân Tích & Sáng Tạo", 
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
        
        lbl_proj = ctk.CTkLabel(proj_container, text="📁 Dự án:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_proj.pack(side="left", padx=(0, 6))
        
        self.proj_combobox = ctk.CTkComboBox(
            proj_container,
            values=["Chưa có dự án"],
            command=self.on_project_combobox_change,
            height=32,
            width=240
        )
        self.proj_combobox.pack(side="left", padx=(0, 6))
        
        self.btn_new_project = ctk.CTkButton(
            proj_container,
            text="+ Tạo Dự Án",
            height=32,
            width=90,
            command=self.create_quick_project,
            **primary_button_kwargs()
        )
        self.btn_new_project.pack(side="left")

        # Tab Views for Flow 1 and Flow 2
        self.tab_flow1 = ctk.CTkTabview(self.workspace_frame, corner_radius=12, fg_color=COLORS["surface"])
        self.tab_flow2 = ctk.CTkTabview(self.workspace_frame, corner_radius=12, fg_color=COLORS["surface"])
        
        # Tabs for Flow 1 (🎬 Cắt Ghép Video)
        self.tab_flow1.add("📋 Sản phẩm")
        self.tab_flow1.add("🔍 Tìm nguyên liệu")
        self.tab_flow1.add("✂️ Cắt clip")
        self.tab_flow1.add("🎞️ Cắt thủ công")
        self.tab_flow1.add("📦 Kho clip")
        self.tab_flow1.add("🎬 Dựng video")
        self.tab_flow1.add("✅ Kết quả")
        
        # Tabs for Flow 2 (🧠 AI Phân Tích & Sáng Tạo)
        self.tab_flow2.add("📚 Học & Duyệt")
        self.tab_flow2.add("💡 Ý Tưởng")
        self.tab_flow2.add("📝 Kịch Bản")
        self.tab_flow2.add("🎙️ Giọng Đọc")
        self.tab_flow2.add("🖼️ Storyboard")
        self.tab_flow2.add("⚙️ Công Việc AI")
        self.tab_flow2.add("Assistant")
        self.tab_flow2.add("🛠️ Cài Đặt")

        # Build tabs
        self.build_tab_product()
        self.build_tab_materials()
        self.build_tab_clip_cutting()
        self.build_tab_manual_cutting()
        self.build_tab_clip_library()
        self.build_tab_editor()
        self.build_tab_results()
        
        self.build_tab_learn_and_review()   # merged: Trí Thức AI + Duyệt học hỏi
        self.build_tab_idea_engine()
        self.build_tab_script()
        self.build_tab_audio()
        self.build_tab_storyboard()
        self.build_tab_agent_jobs()
        self.build_tab_assistant()
        self.build_tab_settings_merged()    # merged: Biên dịch Prompt + Cấu hình
        
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
        tab = self.tab_flow1.tab("📋 Sản phẩm")
        tab.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(tab, text="Thông Tin Sản Phẩm Đang Đánh Giá", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(15, 10))
        
        # Inputs
        self.in_prod_name = LabeledEntry(tab, "Tên dự án / sản phẩm *", "Ví dụ: Giá đỡ điện thoại xoay 360 độ")
        self.in_prod_name.pack(fill="x", padx=20, pady=5)
        
        self.in_prod_desc = LabeledTextbox(tab, "Mô tả sản phẩm ngắn gọn", height=70)
        self.in_prod_desc.pack(fill="x", padx=20, pady=5)
        
        # Price and USP (selling points) in 1 row
        row1 = ctk.CTkFrame(tab, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=5)
        row1.grid_columnconfigure(0, weight=1)
        row1.grid_columnconfigure(1, weight=2)
        
        self.in_prod_price = LabeledEntry(row1, "Giá bán sản phẩm", "Ví dụ: 350.000 VNĐ")
        self.in_prod_price.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.in_prod_usp = LabeledEntry(row1, "Điểm bán hàng cốt lõi (USP)", "Ví dụ: Áp lực nước 1400 lần/phút, 4 chế độ rung")
        self.in_prod_usp.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # Audience and Pain Points in 1 row
        row2 = ctk.CTkFrame(tab, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=5)
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)
        
        self.in_prod_audience = LabeledEntry(row2, "Đối tượng mục tiêu", "Ví dụ: Niềng răng, dân văn phòng, học sinh")
        self.in_prod_audience.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.in_prod_pain = LabeledEntry(row2, "Nỗi đau / Vấn đề của họ (Pain Points)", "Ví dụ: Thức ăn giắt kẽ răng khó lấy, sâu răng do chải răng không sạch")
        self.in_prod_pain.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # Buttons
        self.btn_save_project = ctk.CTkButton(
            tab, 
            text="Khởi Tạo / Lưu Dự Án", 
            command=self.save_project, 
            height=40, 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_save_project.pack(fill="x", padx=20, pady=25)

    def build_tab_materials(self):
        tab = self.tab_flow1.tab("🔍 Tìm nguyên liệu")
        
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
        
        tab_h1 = self.material_tabs.add("Hướng 1: Tên sản phẩm")
        tab_h2 = self.material_tabs.add("Hướng 2: URL sản phẩm")
        tab_other = self.material_tabs.add("Cấu hình khác")
        
        # --- Hướng 1 Layout ---
        self.in_h1_query = ctk.CTkEntry(tab_h1, placeholder_text="Nhập tên sản phẩm (ví dụ: Giá đỡ điện thoại xoay 360 độ)", height=32)
        self.in_h1_query.pack(fill="x", pady=(5, 4))
        
        kw_lbl = ctk.CTkLabel(tab_h1, text="Từ khóa tìm kiếm (Search terms):", font=ctk.CTkFont(size=11, weight="bold"))
        kw_lbl.pack(anchor="w", pady=(0, 2))
        
        self.in_keywords_display = ctk.CTkTextbox(tab_h1, height=75)
        self.in_keywords_display.pack(fill="x", pady=(0, 4))
        
        row_keyword_actions = ctk.CTkFrame(tab_h1, fg_color="transparent")
        row_keyword_actions.pack(fill="x", pady=(0, 4))
        row_keyword_actions.grid_columnconfigure(0, weight=1)
        row_keyword_actions.grid_columnconfigure(1, weight=1)

        self.btn_gen_kw = ctk.CTkButton(
            row_keyword_actions,
            text="AI mở rộng key",
            command=self.generate_project_keywords,
            fg_color="#3b82f6",
            hover_color="#2563eb",
            height=28
        )
        self.btn_gen_kw.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        
        self.btn_run_translate_zh = ctk.CTkButton(
            row_keyword_actions, 
            text="Dịch key", 
            command=self.run_manual_translation_zh, 
            fg_color="#8b5cf6", 
            hover_color="#7c3aed",
            height=28
        )
        self.btn_run_translate_zh.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        
        self.in_translate_zh_result = LabeledEntry(tab_h1, "Kết quả dịch key tiếng Trung:", "Kết quả dịch sẽ xuất hiện ở đây...")
        self.in_translate_zh_result.pack(fill="x", pady=(2, 2))
        
        # --- Hướng 2 Layout ---
        self.in_h2_url = ctk.CTkEntry(tab_h2, placeholder_text="Dán URL sản phẩm Shopee ở đây...", height=32)
        self.in_h2_url.pack(fill="x", pady=(15, 6))
        
        lbl_h2_desc = ctk.CTkLabel(tab_h2, text="💡 Hệ thống sẽ tự động quét thông tin từ trang Shopee,\nTải luôn video gốc của gian hàng và dùng AI trích xuất từ khóa\ncốt lõi để tiếp tục lùng sục phôi review trên MXH.", font=ctk.CTkFont(size=11), text_color="#aaaaaa", justify="left")
        lbl_h2_desc.pack(anchor="w", pady=5)
        
        # --- Cấu hình khác Layout ---
        # 1. URL Paste
        self.prov_urls_var = ctk.StringVar(value="off")
        self.cb_urls = ctk.CTkCheckBox(tab_other, text="Tải từ danh sách URL tự dán", variable=self.prov_urls_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_urls.pack(anchor="w", pady=(2, 2))
        
        self.in_urls_paste = ctk.CTkTextbox(tab_other, height=45)
        self.in_urls_paste.pack(fill="x", pady=(0, 4))
        
        # 2. Supplier Feed
        self.prov_feed_var = ctk.StringVar(value="off")
        self.cb_feed = ctk.CTkCheckBox(tab_other, text="Tải từ Supplier Feed (CSV/JSON)", variable=self.prov_feed_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_feed.pack(anchor="w", pady=1)
        
        row_feed = ctk.CTkFrame(tab_other, fg_color="transparent")
        row_feed.pack(fill="x", pady=(0, 4))
        self.btn_select_feed = ctk.CTkButton(row_feed, text="Chọn Feed", command=self.select_feed_file, width=80, height=22, font=ctk.CTkFont(size=10))
        self.btn_select_feed.pack(side="left")
        self.lbl_feed_status = ctk.CTkLabel(row_feed, text="Chưa chọn", font=ctk.CTkFont(size=10), text_color="#888888")
        self.lbl_feed_status.pack(side="left", padx=5)
        
        # 3. AI Video
        self.prov_ai_video_var = ctk.StringVar(value="off")
        self.cb_ai_video = ctk.CTkCheckBox(tab_other, text="Sinh phôi bằng AI Video (Runway/Pika)", variable=self.prov_ai_video_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
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
        
        self.ai_video_duration = ctk.CTkEntry(ai_video_row, placeholder_text="Giây", height=22, width=35, font=ctk.CTkFont(size=10))
        self.ai_video_duration.pack(side="left", padx=(2, 0))
        self.ai_video_duration.insert(0, "5")
        
        # 4. Cookies Option
        row_cookie = ctk.CTkFrame(tab_other, fg_color="transparent")
        row_cookie.pack(fill="x", pady=(2, 2))
        cookie_lbl = ctk.CTkLabel(row_cookie, text="Cookie trình duyệt:", font=ctk.CTkFont(size=10))
        cookie_lbl.pack(side="left", padx=(0, 5))
        self.browser_cookies_combo = ctk.CTkComboBox(row_cookie, values=["Không dùng cookie", "chrome", "edge", "firefox", "brave", "safari"], state="readonly", height=22, width=120, font=ctk.CTkFont(size=10))
        self.browser_cookies_combo.pack(side="left")
        self.browser_cookies_combo.set("Không dùng cookie")
        
        # --- Providers Option frame (Common bottom area) ---
        prov_lbl = ctk.CTkLabel(opt_frame, text="Chọn nguồn khai thác tài nguyên phôi:", font=ctk.CTkFont(size=11, weight="bold"))
        prov_lbl.pack(anchor="w", pady=(2, 2))
        
        self.prov_prod_images_var = ctk.StringVar(value="on")
        self.cb_prod_images = ctk.CTkCheckBox(opt_frame, text="📸 Tải Ảnh Sản Phẩm HD (Shopee Gallery & Google)", variable=self.prov_prod_images_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_prod_images.pack(anchor="w", pady=1)

        self.prov_social_var = ctk.StringVar(value="on")
        self.cb_social = ctk.CTkCheckBox(opt_frame, text="🎬 Video Review Thực Tế (TikTok / Bilibili / Shorts)", variable=self.prov_social_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_social.pack(anchor="w", pady=1)

        self.prov_shopee_var = ctk.StringVar(value="on")
        self.cb_shopee = ctk.CTkCheckBox(opt_frame, text="🛍️ Video Mô Tả Shopee (Gian hàng chính hãng)", variable=self.prov_shopee_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_shopee.pack(anchor="w", pady=1)

        self.prov_pexels_var = ctk.StringVar(value="off")
        self.cb_pexels = ctk.CTkCheckBox(opt_frame, text="Tìm tải Pexels Video (Stock chung)", variable=self.prov_pexels_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_pexels.pack(anchor="w", pady=1)
        
        self.prov_pixabay_var = ctk.StringVar(value="off")
        self.cb_pixabay = ctk.CTkCheckBox(opt_frame, text="Tìm tải Pixabay Video (Stock chung)", variable=self.prov_pixabay_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_pixabay.pack(anchor="w", pady=1)
        
        # Advanced Processing & Quality Gates
        adv_lbl = ctk.CTkLabel(opt_frame, text="Xử lý nâng cao & Cổng chất lượng (Quality Gate):", font=ctk.CTkFont(size=11, weight="bold"))
        adv_lbl.pack(anchor="w", pady=(6, 2))
        
        self.cb_filter_quality_var = ctk.StringVar(value="on")
        self.cb_filter_quality = ctk.CTkCheckBox(opt_frame, text="🔍 Bộ lọc chất lượng phôi tải về (Local OpenCV)", variable=self.cb_filter_quality_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_filter_quality.pack(anchor="w", pady=1)
        
        self.cb_split_av_var = ctk.StringVar(value="off")
        self.cb_split_av = ctk.CTkCheckBox(opt_frame, text="✂️ Tự động tách âm thanh & hình ảnh phôi MXH", variable=self.cb_split_av_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=11))
        self.cb_split_av.pack(anchor="w", pady=1)
        
        # Run Button
        self.btn_run_downloaders = ctk.CTkButton(opt_frame, text="Bắt Đầu Tải Phôi", command=self.start_downloading_materials, height=35, fg_color="#10b981", hover_color="#059669")
        self.btn_run_downloaders.pack(fill="x", pady=(10, 5))
        
        # Right Console / Log view
        log_lbl = ctk.CTkLabel(log_frame, text="Nhật ký tải phôi:", font=ctk.CTkFont(size=12, weight="bold"))
        log_lbl.pack(anchor="w", pady=4)
        
        self.downloads_console = ConsoleView(log_frame)
        self.downloads_console.pack(fill="both", expand=True)
        
        self.lbl_downloaded_count = ctk.CTkLabel(log_frame, text="Số phôi đã tải thành công: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10b981")
        self.lbl_downloaded_count.pack(anchor="w", pady=(8, 0))

    def build_tab_clip_cutting(self):
        tab = self.tab_flow1.tab("✂️ Cắt clip")
        
        # Left Panel (options) and Right Panel (logs & stats)
        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)
        
        opt_frame = ctk.CTkFrame(tab, fg_color="transparent")
        opt_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        right_frame = ctk.CTkFrame(tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # Section 1: Cấu hình cắt
        lbl_sec1 = ctk.CTkLabel(opt_frame, text="1. Cấu Hình Cắt Clip Phôi:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_sec1.pack(anchor="w", pady=(5, 5))
        
        # Inputs in a row
        row_inputs1 = ctk.CTkFrame(opt_frame, fg_color="transparent")
        row_inputs1.pack(fill="x", pady=2)
        row_inputs1.grid_columnconfigure(0, weight=1)
        row_inputs1.grid_columnconfigure(1, weight=1)
        
        self.in_clip_duration = LabeledEntry(row_inputs1, "Độ dài mỗi clip (giây)", "2.0")
        self.in_clip_duration.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.in_clip_duration.set("2.0")
        
        self.in_skip_start = LabeledEntry(row_inputs1, "Bỏ qua đầu video (giây)", "1.0")
        self.in_skip_start.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.in_skip_start.set("1.0")
        
        self.in_max_clips = LabeledEntry(opt_frame, "Số clip tối đa từ mỗi phôi video", "8")
        self.in_max_clips.pack(fill="x", pady=4)
        self.in_max_clips.set("8")
        
        self.cb_vertical_crop_var = ctk.StringVar(value="on")
        self.cb_vertical_crop = ctk.CTkCheckBox(opt_frame, text="Tự động crop dọc 9:16 (720x1280)", variable=self.cb_vertical_crop_var, onvalue="on", offvalue="off")
        self.cb_vertical_crop.pack(anchor="w", pady=4)
        
        self.cb_mute_clip_var = ctk.StringVar(value="on")
        self.cb_mute_clip = ctk.CTkCheckBox(opt_frame, text="Tắt âm thanh clip phôi (Mute)", variable=self.cb_mute_clip_var, onvalue="on", offvalue="off")
        self.cb_mute_clip.pack(anchor="w", pady=4)
        
        # Section 2: Phân tích chất lượng
        lbl_sec2 = ctk.CTkLabel(opt_frame, text="2. Phân Tích Chất Lượng (OpenCV):", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_sec2.pack(anchor="w", pady=(15, 5))
        
        self.cb_quality_analysis_var = ctk.StringVar(value="on")
        self.cb_quality_analysis = ctk.CTkCheckBox(opt_frame, text="Bật phân tích độ sáng, nét, chuyển động...", variable=self.cb_quality_analysis_var, onvalue="on", offvalue="off")
        self.cb_quality_analysis.pack(anchor="w", pady=4)
        
        self.cb_discard_bad_clips_var = ctk.StringVar(value="off")
        self.cb_discard_bad_clips = ctk.CTkCheckBox(opt_frame, text="Bỏ clip kém chất lượng (loại Reject)", variable=self.cb_discard_bad_clips_var, onvalue="on", offvalue="off")
        self.cb_discard_bad_clips.pack(anchor="w", pady=4)
        
        # Action Buttons
        self.btn_run_clipper = ctk.CTkButton(opt_frame, text="Bắt Đầu Cắt Clip Phôi", command=self.start_clip_cutting, height=35, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_run_clipper.pack(fill="x", pady=(20, 5))
        
        self.btn_open_clips_dir = ctk.CTkButton(opt_frame, text="Mở Thư Mục Clips", command=self.open_clips_dir, height=35, **secondary_button_kwargs())
        self.btn_open_clips_dir.pack(fill="x", pady=5)
        
        # Right Panel: Results & Console
        stats_frame = ctk.CTkFrame(right_frame, fg_color="#121214", corner_radius=8)
        stats_frame.pack(fill="x", pady=(0, 10))
        
        lbl_stats_title = ctk.CTkLabel(stats_frame, text="Báo cáo kết quả phân tích:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_stats_title.pack(anchor="w", padx=15, pady=(8, 4))
        
        row_stats = ctk.CTkFrame(stats_frame, fg_color="transparent")
        row_stats.pack(fill="x", padx=15, pady=(0, 8))
        row_stats.grid_columnconfigure(0, weight=1)
        row_stats.grid_columnconfigure(1, weight=1)
        row_stats.grid_columnconfigure(2, weight=1)
        
        self.lbl_total_clips = ctk.CTkLabel(row_stats, text="Tổng clip đã tạo: 0", font=ctk.CTkFont(size=11, weight="bold"), anchor="w")
        self.lbl_total_clips.grid(row=0, column=0, pady=2, sticky="w")
        
        self.lbl_good_clips = ctk.CTkLabel(row_stats, text="Clip tốt (>=70): 0", font=ctk.CTkFont(size=11), text_color="#22c55e", anchor="w")
        self.lbl_good_clips.grid(row=0, column=1, pady=2, sticky="w")
        
        self.lbl_okay_clips = ctk.CTkLabel(row_stats, text="Clip tạm ổn (>=45): 0", font=ctk.CTkFont(size=11), text_color="#3b82f6", anchor="w")
        self.lbl_okay_clips.grid(row=0, column=2, pady=2, sticky="w")
        
        self.lbl_rejected_clips = ctk.CTkLabel(row_stats, text="Clip bị loại (<45): 0", font=ctk.CTkFont(size=11), text_color="#ef4444", anchor="w")
        self.lbl_rejected_clips.grid(row=1, column=0, pady=2, sticky="w")
        
        self.lbl_failed_clips = ctk.CTkLabel(row_stats, text="Clip lỗi: 0", font=ctk.CTkFont(size=11), text_color="#e2e8f0", anchor="w")
        self.lbl_failed_clips.grid(row=1, column=1, pady=2, sticky="w")
        
        # Console Log
        lbl_log = ctk.CTkLabel(right_frame, text="Nhật ký cắt & phân tích chất lượng:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_log.pack(anchor="w", pady=(5, 4))
        
        self.clip_cutting_console = ConsoleView(right_frame)
        self.clip_cutting_console.pack(fill="both", expand=True)

        self.clip_cutting_console = ConsoleView(right_frame)
        self.clip_cutting_console.pack(fill="both", expand=True)

    def build_tab_manual_cutting(self):
        tab = self.tab_flow1.tab("🎞️ Cắt thủ công")
        
        # Configure layout (Left preview, Right controls)
        tab.grid_columnconfigure(0, weight=5) # Left
        tab.grid_columnconfigure(1, weight=5) # Right
        tab.grid_rowconfigure(0, weight=1)
        
        # Left Panel: Video Frame Preview
        preview_frame = ctk.CTkFrame(tab, fg_color="#121214", corner_radius=12)
        preview_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)
        
        self.manual_preview_label = ctk.CTkLabel(preview_frame, text="Chưa nạp video.\nVui lòng nhấn 'Chọn Video Phôi' ở cột bên phải.", text_color="#71717a")
        self.manual_preview_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Right Panel: Sliders & Settings
        control_frame = ctk.CTkFrame(tab, fg_color="transparent")
        control_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # 1. Video Selection Row
        row_sel = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_sel.pack(fill="x", pady=(5, 5))
        
        btn_select = ctk.CTkButton(row_sel, text="Chọn Video Phôi", command=self.manual_select_video, **secondary_button_kwargs(), width=120)
        btn_select.pack(side="left", padx=(0, 10))
        
        self.lbl_manual_video_name = ctk.CTkLabel(row_sel, text="Chưa chọn video phôi", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa", anchor="w")
        self.lbl_manual_video_name.pack(side="left", fill="x", expand=True)
        
        # 2. Metadata Display
        self.lbl_manual_video_meta = ctk.CTkLabel(control_frame, text="Thời lượng: --s | Kích thước: --x-- | FPS: --", font=ctk.CTkFont(size=11), text_color="#71717a", anchor="w")
        self.lbl_manual_video_meta.pack(fill="x", pady=(0, 15))
        
        # 3. Sliders & Time Inputs
        # Start Time
        lbl_start = ctk.CTkLabel(control_frame, text="Điểm đầu (Start Time):", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
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
        lbl_end = ctk.CTkLabel(control_frame, text="Điểm cuối (End Time):", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
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
        self.lbl_manual_duration = ctk.CTkLabel(control_frame, text="Độ dài đoạn cắt: 0.00s", font=ctk.CTkFont(size=13, weight="bold"), text_color="#60a5fa", anchor="w")
        self.lbl_manual_duration.pack(fill="x", pady=(0, 10))
        
        # 5. Options Checkbox
        row_opts = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_opts.pack(fill="x", pady=(0, 15))
        
        self.cb_manual_vertical_var = ctk.StringVar(value="on")
        self.cb_manual_vertical = ctk.CTkCheckBox(row_opts, text="Tự động crop dọc 9:16", variable=self.cb_manual_vertical_var, onvalue="on", offvalue="off")
        self.cb_manual_vertical.pack(side="left", padx=(0, 15))
        
        self.cb_manual_mute_var = ctk.StringVar(value="on")
        self.cb_manual_mute = ctk.CTkCheckBox(row_opts, text="Tắt âm thanh (Mute)", variable=self.cb_manual_mute_var, onvalue="on", offvalue="off")
        self.cb_manual_mute.pack(side="left")
        
        # 5.5. Save Directory Input
        lbl_save_dir = ctk.CTkLabel(control_frame, text="Thư mục lưu clip cắt:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_save_dir.pack(fill="x", pady=(5, 2))
        
        row_save_dir = ctk.CTkFrame(control_frame, fg_color="transparent")
        row_save_dir.pack(fill="x", pady=(0, 15))
        
        self.in_manual_save_dir = ctk.CTkEntry(row_save_dir, placeholder_text="Đường dẫn thư mục lưu clips...")
        self.in_manual_save_dir.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        btn_browse_save_dir = ctk.CTkButton(row_save_dir, text="Chọn thư mục", width=100, height=28, **secondary_button_kwargs(), command=self.manual_browse_save_dir)
        btn_browse_save_dir.pack(side="left")
        
        # 6. Action Button
        self.btn_manual_cut = ctk.CTkButton(control_frame, text="Bắt Đầu Cắt & Lưu Clip", command=self.start_manual_cut, height=38, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], state="disabled")
        self.btn_manual_cut.pack(fill="x", pady=(0, 10))
        
        # 7. Progress Bar
        self.manual_progress_bar = ctk.CTkProgressBar(control_frame, progress_color="#3b82f6", fg_color="#27272a")
        self.manual_progress_bar.pack(fill="x", pady=(0, 10))
        self.manual_progress_bar.set(0.0)
        
        # 8. Console Log View
        lbl_console = ctk.CTkLabel(control_frame, text="Nhật ký tiến trình cắt:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
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
            title="Chọn Video Phôi",
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
            messagebox.showerror("Lỗi", "Không thể mở video này.")
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
            text=f"Thời lượng: {self.manual_duration:.2f}s | Kích thước: {self.manual_width}x{self.manual_height} | FPS: {self.manual_fps:.1f}"
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
        self.lbl_manual_duration.configure(text=f"Độ dài đoạn cắt: {diff:.2f}s")
        
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
        self.lbl_manual_duration.configure(text=f"Độ dài đoạn cắt: {diff:.2f}s")
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
        self.lbl_manual_duration.configure(text=f"Độ dài đoạn cắt: {diff:.2f}s")
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
            title="Chọn Thư Mục Lưu Clips"
        )
        if target_dir:
            self.in_manual_save_dir.delete(0, "end")
            self.in_manual_save_dir.insert(0, os.path.abspath(target_dir))

    def start_manual_cut(self):
        if not self.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn hoặc tạo dự án trước.")
            return
            
        if not self.manual_video_path:
            return
            
        start_t = float(self.slider_manual_start.get())
        end_t = float(self.slider_manual_end.get())
        duration = end_t - start_t
        
        if duration <= 0.1:
            messagebox.showerror("Khoảng thời gian lỗi", "Độ dài đoạn cắt phải lớn hơn 0.1s.")
            return
            
        save_dir = self.in_manual_save_dir.get().strip()
        if not save_dir:
            messagebox.showerror("Thiếu đường dẫn", "Vui lòng nhập hoặc chọn thư mục lưu clip.")
            return
            
        self.btn_manual_cut.configure(state="disabled", text="Đang cắt...")
        self.manual_progress_bar.set(0.1)
        self.manual_console.clear()
        
        export_vertical = self.cb_manual_vertical_var.get() == "on"
        mute_audio = self.cb_manual_mute_var.get() == "on"
        
        t = threading.Thread(target=self.run_manual_cut_thread, args=(start_t, end_t, export_vertical, mute_audio, save_dir), daemon=True)
        t.start()
        
    def run_manual_cut_thread(self, start_t, end_t, export_vertical, mute_audio, save_dir):
        try:
            self.manual_console.log("[*] Khởi tạo quy trình cắt video thủ công...")
            self.manual_console.log(f"[*] Thư mục lưu kết quả: {save_dir}")
            
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
            self.manual_console.log("[+] Hoàn thành cắt clip thủ công!")
            
            # Notify main thread
            self.after(0, lambda: self.finish_manual_cut(result))
            
        except Exception as e:
            self.manual_console.log(f"[x] Lỗi cắt video: {e}")
            self.after(0, self.on_manual_cut_failed)
            
    def finish_manual_cut(self, result):
        self.btn_manual_cut.configure(state="normal", text="Bắt Đầu Cắt & Lưu Clip")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Thành công", f"Đã cắt và lưu clip thành công:\n{os.path.basename(result['file_path'])}")
        
    def on_manual_cut_failed(self):
        self.btn_manual_cut.configure(state="normal", text="Bắt Đầu Cắt & Lưu Clip")
        self.manual_progress_bar.set(0.0)
        messagebox.showerror("Lỗi cắt", "Cắt clip thủ công thất bại. Xem chi tiết lỗi ở bảng nhật ký.")

    def on_app_closing(self):
        if hasattr(self, 'manual_cap') and self.manual_cap:
            try:
                self.manual_cap.release()
            except Exception:
                pass
        self.destroy()

    def build_tab_script(self):

        tab = self.tab_flow2.tab("📝 Kịch Bản")

        self._script_tab_instance = ScriptGeneratorTab(tab, self)



    def script_refresh_learned_dropdown(self):

        if hasattr(self, "_script_tab_instance"):

            self._script_tab_instance.script_refresh_learned_dropdown()

    def build_tab_audio(self):

        tab = self.tab_flow2.tab("🎙️ Giọng Đọc")

        self._audio_tab_instance = AudioGeneratorTab(tab, self)

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
        tab = self.tab_flow1.tab("🎬 Dựng video")

        tab.grid_columnconfigure(0, weight=4)
        tab.grid_columnconfigure(1, weight=6)
        tab.grid_rowconfigure(0, weight=1)
        
        left_frame = ctk.CTkFrame(tab, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        right_frame = ctk.CTkFrame(tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        # Left Panel (Settings)
        lbl_sett = ctk.CTkLabel(left_frame, text="Cấu Hình Dựng Video:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_sett.pack(anchor="w", pady=4)
        
        self.cb_subtitles_var = ctk.StringVar(value="on")
        self.cb_subtitles = ctk.CTkCheckBox(left_frame, text="Bật phụ đề chữ (Tự động theo kịch bản)", variable=self.cb_subtitles_var, onvalue="on", offvalue="off")
        self.cb_subtitles.pack(anchor="w", pady=8)
        
        self.lbl_editor_summary = ctk.CTkLabel(left_frame, text="Thông tin phôi hiện có:\n- Video phôi: 0\n- Thuyết minh: Chưa có", justify="left")
        self.lbl_editor_summary.pack(anchor="w", pady=15)
        
        self.btn_edit_video = ctk.CTkButton(left_frame, text="Bắt Đầu Dựng Video TikTok (9:16)", command=self.start_video_editor_pipeline, height=40, fg_color="#10b981", hover_color="#059669")
        self.btn_edit_video.pack(fill="x", pady=10)
        
        # Right Panel (Console)
        lbl_log = ctk.CTkLabel(right_frame, text="Nhật ký render video (moviepy):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_log.pack(anchor="w", pady=4)
        
        self.editor_console = ConsoleView(right_frame)
        self.editor_console.pack(fill="both", expand=True)

    def start_video_editor_pipeline(self):
        if not self.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn dự án trước.")
            return

        proj = self.get_current_project_folders()
        if not proj:
            messagebox.showerror("Lỗi", "Không tìm thấy thư mục dự án.")
            return

        self.btn_edit_video.configure(state="disabled", text="⚡ Đang dựng video...")
        self.editor_console.clear()
        self.editor_console.log("[*] Bắt đầu tiến trình dựng video TikTok...")

        add_subs = self.cb_subtitles_var.get() == "on"

        def run_pipeline():
            try:
                from editor.video_editor import build_tiktok_video
                export_path = build_tiktok_video(
                    project_folders=proj,
                    add_subtitles=add_subs,
                    log_callback=self.editor_console.log
                )
                self.after(0, lambda: self.finish_video_editing(export_path))
            except Exception as e:
                self.after(0, lambda: self.on_video_editing_failed(str(e)))

        import threading
        threading.Thread(target=run_pipeline, daemon=True).start()

    def finish_video_editing(self, export_path):
        self.btn_edit_video.configure(state="normal", text="Bắt Đầu Dựng Video TikTok (9:16)")
        self.editor_console.log(f"[✅] Dựng video thành công! Đầu ra: {export_path}")
        
        self.btn_open_export_dir.configure(state="normal")
        self.lbl_video_result_status.configure(text=f"✓ Video đã dựng xong! File: {os.path.basename(export_path)}", text_color="#4ade80")
        
        proj = self.get_current_project_folders()
        if proj:
            script_path = os.path.join(proj["scripts"], "voice_script.txt")
            if os.path.exists(script_path):
                with open(script_path, "r", encoding="utf-8") as f:
                    self.caption_display_box.delete("1.0", "end")
                    self.caption_display_box.insert("1.0", f.read().strip())
        
        messagebox.showinfo("Thành công", f"Đã dựng video thành công!\nFile: {export_path}")

    def on_video_editing_failed(self, err):
        self.btn_edit_video.configure(state="normal", text="Bắt Đầu Dựng Video TikTok (9:16)")
        self.editor_console.log(f"[❌] Lỗi dựng video: {err}")
        messagebox.showerror("Lỗi dựng video", f"Không thể dựng video:\n{err}")

    def build_tab_results(self):
        tab = self.tab_flow1.tab("✅ Kết quả")
        tab.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(tab, text="Kết Quả Xuất Video & Đăng Bài", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(15, 10))
        
        self.lbl_video_result_status = ctk.CTkLabel(tab, text="Video chưa được dựng. Vui lòng hoàn thành Tab 'Dựng video'.", font=ctk.CTkFont(size=13), text_color="#e2e8f0")
        self.lbl_video_result_status.pack(anchor="w", padx=20, pady=5)
        
        row_act = ctk.CTkFrame(tab, fg_color="transparent")
        row_act.pack(fill="x", padx=20, pady=10)
        
        self.btn_open_export_dir = ctk.CTkButton(row_act, text="Mở Thư Mục Chứa Video", command=self.open_export_dir, **secondary_button_kwargs(), state="disabled")
        self.btn_open_export_dir.pack(side="left")
        
        # Caption & Hashtags to easily copy
        self.caption_display_box = LabeledTextbox(tab, "Caption gợi ý để copy đăng TikTok:", height=70)
        self.caption_display_box.pack(fill="x", padx=20, pady=5)
        
        self.hashtags_display_box = LabeledTextbox(tab, "Hashtags gợi ý để copy:", height=50)
        self.hashtags_display_box.pack(fill="x", padx=20, pady=5)

    def open_export_dir(self):
        if not self.active_project_slug:
            return
        proj = self.get_current_project_folders()
        if proj and os.path.exists(proj["root"]):
            os.startfile(proj["root"])

    def build_tab_storyboard(self):

        tab = self.tab_flow2.tab("🖼️ Storyboard")

        self._storyboard_tab_instance = StoryboardTab(tab, self)



    def save_storyboard(self):

        if hasattr(self, "_storyboard_tab_instance"):

            self._storyboard_tab_instance.save_storyboard()

    # ==================== AGENT JOBS TAB ====================

    # ==================== AGENT JOBS TAB ====================

    def build_tab_agent_jobs(self):
        
        tab = self.tab_flow2.tab("⚙️ Công Việc AI")
        
        self._agent_jobs_tab_instance = AgentJobsTab(tab, self)

    def build_tab_assistant(self):
        tab = self.tab_flow2.tab("Assistant")
        self._assistant_tab_instance = AssistantTab(tab, self)
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
                text="Chưa có đề xuất nào cần duyệt.\nHệ thống đang vận hành ổn định.",
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
            meta_text = "Đề xuất học hỏi mới"
            if path and os.path.exists(path):
                try:
                    sz = os.path.getsize(path)
                    meta_text = f"Dung lượng: {sz} bytes"
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
                text="Xem chi tiết",
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
            self.lbl_preview_title.configure(text="📄 Xem Chi Tiết Đề Xuất")
            self.btn_approve_review.grid()
            self.btn_reject_review.grid()
            
        if not choice:
            self.current_review_selection = None
            self.review_textboxes["Tóm tắt"].insert("1.0", "Chưa có proposal nào trong knowledge_base/review_queue.\n\nWorker/Codex có thể ghi lesson hoặc prompt proposal vào folder này để anh duyệt.")
            return
            
        self.current_review_selection = choice
        content = self.learning_review_store.read(choice) or "(Empty proposal)"
        
        import re
        if "### Công cụ & Khái niệm:" in content:
            parts = re.split(r'### Công cụ & Khái niệm:|### Quy trình:|### Ứng dụng cho Hermes:', content)
            summary_part = parts[0].strip() if len(parts) >= 1 else content
            concepts_part = parts[1].strip() if len(parts) >= 2 else ""
            workflow_part = parts[2].strip() if len(parts) >= 3 else ""
            analysis_combined = f"【 CÔNG CỤ & KHÁI NIỆM 】\n{concepts_part}\n\n【 QUY TRÌNH 】\n{workflow_part}"
            hermes_part = parts[3].strip() if len(parts) >= 4 else "Không có dữ liệu."
            
            self.review_textboxes["Tóm tắt"].insert("1.0", summary_part)
            self.review_textboxes["Phân tích"].insert("1.0", analysis_combined)
            self.review_textboxes["Setup"].insert("1.0", f"【 ỨNG DỤNG CHO HERMES 】\n{hermes_part}")
            self.review_textboxes["Prompt"].insert("1.0", "Loại Knowledge Proposal này không có Prompt Mapping cụ thể.")
        else:
            parts = re.split(r'### Phân tích Hook/Body/CTA:|### Quay dựng & Setup:|### Prompt Mapping:', content)
            summary_part = parts[0].strip() if len(parts) >= 1 else content
            analysis_part = parts[1].strip() if len(parts) >= 2 else "Không có dữ liệu phân tích."
            setup_part = parts[2].strip() if len(parts) >= 3 else "Không có dữ liệu setup."
            prompt_part = parts[3].strip() if len(parts) >= 4 else "Không có dữ liệu prompt."
            
            self.review_textboxes["Tóm tắt"].insert("1.0", summary_part)
            self.review_textboxes["Phân tích"].insert("1.0", analysis_part)
            self.review_textboxes["Setup"].insert("1.0", setup_part)
            self.review_textboxes["Prompt"].insert("1.0", prompt_part)

    def approve_learning_review(self):
        name = getattr(self, "current_review_selection", None)
        if not name:
            messagebox.showinfo("Learning review", "Vui lòng chọn một đề xuất để duyệt.")
            return
        try:
            target = self.learning_review_store.approve(name)
            messagebox.showinfo("Thành công", f"Đã duyệt và lưu bài học thành công!")
            self.current_review_selection = None
            self.refresh_learning_reviews()
        except Exception as exc:
            messagebox.showerror("Approve failed", str(exc))

    def reject_learning_review(self):
        name = getattr(self, "current_review_selection", None)
        if not name:
            messagebox.showinfo("Learning review", "Vui lòng chọn một đề xuất để từ chối.")
            return
        try:
            target = self.learning_review_store.reject(name)
            messagebox.showinfo("Thành công", f"Đã từ chối đề xuất này.")
            self.current_review_selection = None
            self.refresh_learning_reviews()
        except Exception as exc:
            messagebox.showerror("Reject failed", str(exc))

    def build_tab_idea_engine(self):

        tab = self.tab_flow2.tab("💡 Ý Tưởng")

        self._idea_engine_tab_instance = IdeaEngineTab(tab, self)



    def _render_idea_cards(self, ideas):

        if hasattr(self, "_idea_engine_tab_instance"):

            self._idea_engine_tab_instance._render_idea_cards(ideas)

    # ==================== CLIP LIBRARY TAB ====================

    def build_tab_clip_library(self):
        """Tab Kho Phôi — quản lý clip library của project."""
        tab = self.tab_flow1.tab("📦 Kho clip")
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=7)
        tab.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Controls & Stats ---
        left = ctk.CTkScrollableFrame(tab, fg_color="transparent", width=260)
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        ctk.CTkLabel(left, text="📦 Kho Phôi", font=ctk.CTkFont(size=16, weight="bold"), text_color="#f59e0b").pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(left, text="Quản lý, review và tag các clip phôi\ncủa dự án hiện tại", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left").pack(anchor="w", pady=(0, 12))

        # Import buttons
        self.btn_lib_import = ctk.CTkButton(
            left, text="➕ Import Clips Vào Kho", command=self.lib_import_clips,
            height=36, fg_color="#f59e0b", hover_color="#d97706",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#000000"
        )
        self.btn_lib_import.pack(fill="x", pady=(4, 4))

        self.btn_lib_open_dir = ctk.CTkButton(
            left, text="📁 Mở Thư Mục Kho Phôi", command=self.lib_open_dir,
            height=30, **secondary_button_kwargs()
        )
        self.btn_lib_open_dir.pack(fill="x", pady=4)

        ctk.CTkFrame(left, height=1, fg_color="#2d2d34").pack(fill="x", pady=8)

        # Filters
        ctk.CTkLabel(left, text="Lọc clips:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(4, 4))

        ctk.CTkLabel(left, text="Theo trạng thái:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.lib_filter_status = ctk.CTkComboBox(
            left,
            values=["Tất cả"] + CLIP_STATUSES,
            command=lambda v: self.lib_refresh_cards(),
            state="readonly", height=28
        )
        self.lib_filter_status.pack(fill="x", pady=(2, 6))
        self.lib_filter_status.set("Tất cả")

        ctk.CTkLabel(left, text="Theo loại phôi:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.lib_filter_asset = ctk.CTkComboBox(
            left,
            values=["Tất cả"] + ASSET_TYPES,
            command=lambda v: self.lib_refresh_cards(),
            state="readonly", height=28
        )
        self.lib_filter_asset.pack(fill="x", pady=(2, 6))
        self.lib_filter_asset.set("Tất cả")

        # Search
        ctk.CTkLabel(left, text="Tìm kiếm (tên / tag):", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.lib_search_var = ctk.StringVar()
        self.lib_search_var.trace_add("write", lambda *a: self.lib_refresh_cards())
        self.lib_search_entry = ctk.CTkEntry(left, textvariable=self.lib_search_var, placeholder_text="Nhập từ khóa...", height=28)
        self.lib_search_entry.pack(fill="x", pady=(2, 10))

        ctk.CTkFrame(left, height=1, fg_color="#2d2d34").pack(fill="x", pady=6)

        # Stats
        ctk.CTkLabel(left, text="Thống kê kho phôi:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(4, 4))
        self.lib_stats_lbl = ctk.CTkLabel(left, text="Chưa có clip nào", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left")
        self.lib_stats_lbl.pack(anchor="w")

        # Refresh
        ctk.CTkButton(
            left, text="🔄 Làm mới", command=self.lib_refresh_cards,
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
            text="Kho phôi trống.\nNhấn '➕ Import Clips Vào Kho' để thêm phôi video.",
            font=ctk.CTkFont(size=13), text_color="#4b5563"
        )
        self.lib_placeholder_lbl.pack(pady=80)

    # --- CLIP LIBRARY ACTIONS ---

    def _ensure_clip_library(self):
        """Khởi tạo ClipLibrary cho project đang active."""
        if not self.active_project_slug:
            return False
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        self.clip_library = ClipLibrary(folders["root"])
        return True

    def lib_import_clips(self):
        """Import nhiều file video vào Kho Phôi."""
        if not self._ensure_clip_library():
            messagebox.showerror("Lỗi", "Vui lòng chọn dự án trước.")
            return

        files = filedialog.askopenfilenames(
            title="Chọn các file clip để import vào Kho Phôi",
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

        messagebox.showinfo("Import xong", f"Đã import {added} clip vào Kho Phôi.\nTrạng thái ban đầu: pending\nBạn có thể đổi trạng thái và thêm tag cho từng clip.")
        self.lib_refresh_cards()

    def lib_open_dir(self):
        """Mở thư mục clip_library của project."""
        if not self.active_project_slug:
            return
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        lib_dir = os.path.join(folders["root"], "clip_library")
        os.makedirs(lib_dir, exist_ok=True)
        try:
            os.startfile(lib_dir)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được thư mục: {e}")

    def lib_refresh_cards(self):
        """Refresh danh sách clip cards theo filter hiện tại."""
        if not self._ensure_clip_library():
            return

        status_f = self.lib_filter_status.get()
        asset_f = self.lib_filter_asset.get()
        query = self.lib_search_var.get().strip()

        clips = self.clip_library.search_clips(
            query=query,
            status_filter=None if status_f == "Tất cả" else status_f,
            asset_type_filter=None if asset_f == "Tất cả" else asset_f,
        )

        # Update stats
        stats = self.clip_library.get_stats()
        stats_text = (
            f"Tổng: {stats['total']} clip | {stats['total_duration']}s\n"
            f"✅ Approved: {stats['approved']}\n"
            f"🟡 Okay: {stats['okay']}\n"
            f"⏳ Pending: {stats['pending']}\n"
            f"❌ Rejected: {stats['rejected']}\n"
            f"✂️ Needs Cut: {stats['needs_cut']}"
        )
        self.lib_stats_lbl.configure(text=stats_text)

        # Clear old cards
        for w in self.lib_cards_frame.winfo_children():
            w.destroy()

        if not clips:
            ctk.CTkLabel(
                self.lib_cards_frame,
                text="Không có clip nào.\nThử đổi bộ lọc hoặc import clips mới.",
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
            "approved": "✅ Approved",
            "okay": "🟡 Okay",
            "pending": "⏳ Pending",
            "rejected": "❌ Rejected",
            "needs_cut": "✂️ Needs Cut",
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
                    ctk.CTkLabel(thumb_col, text="🎬", font=ctk.CTkFont(size=24), text_color="#4b5563").pack(expand=True)
            else:
                ctk.CTkLabel(thumb_col, text="🎬", font=ctk.CTkFont(size=24), text_color="#4b5563").pack(expand=True)

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
            ctk.CTkLabel(info_col, text=f"⏱ {dur:.1f}s  |  📐 {w}×{h}  |  ⭐ Q:{q}", font=ctk.CTkFont(size=11), text_color="#94a3b8", anchor="w").pack(fill="x", pady=2)

            # Tags
            tags = clip.get("tags", [])
            tags_text = "  ".join([f"#{t}" for t in tags]) if tags else "Chưa có tag"
            ctk.CTkLabel(info_col, text=tags_text, font=ctk.CTkFont(size=10), text_color="#6b7280", anchor="w").pack(fill="x")

            # Action buttons
            btn_row = ctk.CTkFrame(info_col, fg_color="transparent")
            btn_row.pack(fill="x", pady=(6, 0))

            clip_id = clip["clip_id"]

            for new_status, btn_label, btn_color in [
                ("approved", "✅", "#10b981"),
                ("okay", "🟡", "#f59e0b"),
                ("rejected", "❌", "#ef4444"),
                ("needs_cut", "✂️", "#8b5cf6"),
            ]:
                ctk.CTkButton(
                    btn_row, text=btn_label, width=32, height=26,
                    fg_color="#2e2e38", hover_color=btn_color,
                    command=lambda cid=clip_id, ns=new_status: self.lib_update_status(cid, ns)
                ).pack(side="left", padx=(0, 3))

            # Tag input
            tag_entry = ctk.CTkEntry(btn_row, placeholder_text="Thêm tag...", height=26, width=100)
            tag_entry.pack(side="left", padx=(8, 3))
            ctk.CTkButton(
                btn_row, text="+ Tag", width=50, height=26,
                **secondary_button_kwargs(),
                command=lambda cid=clip_id, e=tag_entry: self.lib_add_tag(cid, e.get().strip())
            ).pack(side="left")

            # Notes
            notes = clip.get("notes", "")
            if notes:
                ctk.CTkLabel(info_col, text=f"📝 {notes}", font=ctk.CTkFont(size=10), text_color="#6b7280", anchor="w").pack(fill="x", pady=(2, 0))

    def lib_update_status(self, clip_id, new_status):
        """Cập nhật status cho clip."""
        if self.clip_library:
            self.clip_library.update_clip(clip_id, status=new_status)
            self.lib_refresh_cards()

    def lib_add_tag(self, clip_id, tag):
        """Thêm tag vào clip."""
        if not tag or not self.clip_library:
            return
        clip = next((c for c in self.clip_library.get_all_clips() if c["clip_id"] == clip_id), None)
        if clip:
            tags = clip.get("tags", [])
            if tag not in tags:
                tags.append(tag)
                self.clip_library.update_clip(clip_id, tags=tags)
                self.lib_refresh_cards()

    # ==================== KNOWLEDGE HUB (AI LEARNING) ====================

    def build_tab_knowledge_hub(self):
        """Deprecated: functionality merged into build_tab_learn_and_review."""
        pass


    def start_knowledge_learning(self):
        """Kích hoạt tiến trình tải và phân tích video YouTube/TikTok."""
        url = self.in_kb_url.get().strip()
        if not url:
            messagebox.showerror("Thiếu thông tin", "Vui lòng nhập link video để học hỏi.")
            return

        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lỗi Gemini", "Chưa nhập Gemini API Key. Vui lòng cấu hình ở tab Cấu hình.")
            return

        category = self.kb_category_combo.get()
        self.btn_kb_learn.configure(state="disabled", text="⏳ Đang học hỏi...")
        self.kb_console.clear()

        def run():
            result = kb.learn_from_url(url, category, log_callback=self.kb_console.log, auto_approve=True, approved_by="gui_user", approval_mode="auto")
            self.after(0, lambda: self.finish_knowledge_learning(result))

        threading.Thread(target=run, daemon=True).start()

    def finish_knowledge_learning(self, result):
        """Xử lý kết quả trả về sau khi hoàn thành tiến trình học."""
        self.btn_kb_learn.configure(state="normal", text="🧠 Bắt Đầu Học Hỏi (AI Learn)")
        
        if "error" in result:
            messagebox.showerror("Lỗi học hỏi", result["error"])
            return

        slug = result.get("slug")
        title = result.get("title", "Bài học")
        self.in_kb_url.set("")
        self.kb_refresh_list()
        
        # Load details of new learned video
        self.kb_view_item(slug)
        
        # Refresh script dropdown in script tab
        self.script_refresh_learned_dropdown()
        
        messagebox.showinfo("Thành công", f"Đã học xong video mẫu:\n'{title}'\n\nBạn có thể áp dụng phong cách này trong tab Kịch bản!")

    def kb_refresh_list(self):
        """Cập nhật giao diện danh sách bài học đã lưu."""
        for widget in self.kb_list_scroll.winfo_children():
            widget.destroy()

        learned_list = kb.load_learned_list()
        if not learned_list:
            lbl = ctk.CTkLabel(
                self.kb_list_scroll, 
                text="Chưa có bài học nào.\nHãy dán link ở cột trái để AI học.", 
                font=ctk.CTkFont(size=12),
                text_color="#4b5563"
            )
            lbl.pack(pady=40)
            return

        # Render list in reverse order (newest first)
        for item in reversed(learned_list):
            slug = item.get("slug")
            title = item.get("title", "Bài học")
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

            meta_text = f"Nguồn: {platform}  |  Phân loại: {category}"
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
                text="Xem bài học", 
                width=80, 
                height=24,
                fg_color="#10b981", 
                hover_color="#059669",
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda s=slug: self.kb_view_item(s)
            ).pack(side="left", padx=(0, 5))

            ctk.CTkButton(
                act_row, 
                text="Xóa", 
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
            self.lbl_preview_title.configure(text="📄 Chi Tiết Bài Học Đã Lưu")
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
            
            if summary: self.review_textboxes["Tóm tắt"].insert("1.0", summary)
            else: self.review_textboxes["Tóm tắt"].insert("1.0", "(Không có nội dung tóm tắt từ file)")
                
            if analysis: self.review_textboxes["Phân tích"].insert("1.0", analysis)
            else: self.review_textboxes["Phân tích"].insert("1.0", "(Không có nội dung phân tích từ file)")
                
            if setup: self.review_textboxes["Setup"].insert("1.0", setup)
            else: self.review_textboxes["Setup"].insert("1.0", "(Không có nội dung setup từ file)")
                
            if prompt: self.review_textboxes["Prompt"].insert("1.0", prompt)
            else: self.review_textboxes["Prompt"].insert("1.0", "(Không có nội dung prompt từ file)")
            return

        # Fallback to DB entry data
        detail = kb.get_learned_detail(slug)
        if not detail:
            self.review_textboxes["Tóm tắt"].insert("1.0", "Không tìm thấy dữ liệu chi tiết của bài học này.")
            return
        
        title = detail.get("title", "")
        platform = detail.get("platform", "YouTube")
        transcript = detail.get("transcript", "")
        structure = detail.get("structure", "")
        copywriting = detail.get("copywriting_style", "")
        lessons = detail.get("key_lessons", "")

        summary_md = f"# TIÊU ĐỀ: {title}\n- Nền tảng: {platform}\n\n## BÀI HỌC QUAN TRỌNG:\n{lessons}"
        analysis_md = f"## 1. CẤU TRÚC KỊCH BẢN (HOOK - BODY - CTA):\n{structure}\n\n## 2. PHONG CÁCH HÀNH VĂN:\n{copywriting}"
        setup_md = "(Không có dữ liệu setup quay dựng trong DB)"
        prompt_md = f"## LỜI THOẠI CHI TIẾT (TRANSCRIPT):\n{transcript}"

        self.review_textboxes["Tóm tắt"].insert("1.0", summary_md)
        self.review_textboxes["Phân tích"].insert("1.0", analysis_md)
        self.review_textboxes["Setup"].insert("1.0", setup_md)
        self.review_textboxes["Prompt"].insert("1.0", prompt_md)

    def kb_delete_item(self, slug):
        """Xóa bài học khỏi kho dữ liệu."""
        detail = kb.get_learned_detail(slug)
        title = detail.get("title", "Bài học") if detail else "Bài học này"
        
        ans = messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc chắn muốn xóa bài học:\n'{title}'\nkhỏi Kho tri thức không?")
        if ans:
            kb.delete_learned_item(slug)
            self.kb_refresh_list()
            
            # Clear textboxes
            for tb in self.review_textboxes.values():
                tb.delete("1.0", "end")
            self.review_textboxes["Tóm tắt"].insert("1.0", "Đã xóa bài học thành công.")
            
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
            self.gemini_ind.set_info("ĐÃ CẤU HÌNH KEY")
        else:
            self.gemini_ind.set_error("CHƯA CÓ KEY")

    def check_gemini(self):
        """Actively checks if the Gemini API Key is working by hitting the endpoint."""
        api_key = config.GEMINI_API_KEY
        if not api_key:
            self.gemini_ind.set_error("THIẾU KEY API")
            messagebox.showerror("Lỗi Cấu Hình", "Gemini API Key trống. Vui lòng nhập khóa API ở tab Cấu hình.")
            return False
            
        self.gemini_ind.set_info("ĐANG GỬI THỬ...")
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": "Say OK"}]}]}
        try:
            r = requests.post(url, json=payload, timeout=8)
            if r.status_code == 200:
                self.gemini_ind.set_ok("KẾT NỐI OK")
                messagebox.showinfo("Kiểm tra thành công", "Đã kết nối thành công với Google Gemini API!")
                return True
            else:
                self.gemini_ind.set_error("LỖI API KEY")
                messagebox.showerror("Lỗi Gemini API", f"Mã lỗi HTTP {r.status_code}: {r.text}")
        except Exception as e:
            self.gemini_ind.set_error("LỖI KẾT NỐI")
            messagebox.showerror("Lỗi Kết Nối", f"Không thể kết nối đến Gemini API: {e}")
        return False

    # --- PROJECT FLOW ACTIONS ---
    
    def load_project_list(self):
        """Scans folder and reloads the project combobox dropdown."""
        projects = self.project_manager.list_projects()
        if not projects:
            self.proj_combobox.configure(values=["Chưa có dự án"])
            self.proj_combobox.set("Chưa có dự án")
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
        if value == "Chưa có dự án":
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
        self.lbl_downloaded_count.configure(text=f"Số phôi đã tải thành công: {len(mats)}")
        
        # Tab 3 (Cắt clip phôi)
        self.refresh_clip_statistics()
        
        # Tab 4 (Script)
        script_info = meta.get('scripts', {})
        voice_script = script_info.get('voice_script', '')
        if voice_script:
            self.script_display_box.set(voice_script)
            style_name = script_info.get('style', 'Mở đầu tò mò')
            style_map = {
                "Curiosity hook": "Mở đầu tò mò",
                "Pain-point hook": "Đánh thẳng nỗi đau",
                "Before/after hook": "Trước và sau",
                "Honest review style": "Đánh giá chân thực",
                "Cheap but useful style": "Ngon bổ rẻ",
                "Viral TikTok style": "TikTok Viral (Bắt trend)"
            }
            mapped_style = style_map.get(style_name, style_name)
            if mapped_style in SCRIPT_STYLES:
                self.script_style_combo.set(mapped_style)
        else:
            self.script_display_box.set("Chưa sinh kịch bản. Vui lòng chọn phong cách và tạo kịch bản.")
            
        # Tab 5 (Audio)
        audio_info = meta.get('audio', {})
        audio_name = audio_info.get('file_name', '')
        duration = audio_info.get('duration', 0.0)
        
        if audio_name and duration > 0:
            self.lbl_audio_status.configure(text=f"Đã nạp: {audio_name}", text_color="#10b981")
            self.lbl_audio_duration.configure(text=f"Độ dài âm thanh thuyết minh: {duration:.2f} giây")
        else:
            self.lbl_audio_status.configure(text="Chưa nạp âm thanh (.mp3)", text_color="#ef4444")
            self.lbl_audio_duration.configure(text="Độ dài âm thanh thuyết minh: Chưa đo")
            
        # Tab 6 (Editor info)
        clips_count = sum(1 for c in meta.get("clips", []) if c.get("status") == "Generated" and not c.get("deleted", False))
        self.lbl_editor_summary.configure(text=f"Thông tin phôi hiện có:\n- Video phôi gốc: {len(mats)} file\n- Clip đã cắt dọc: {clips_count} file\n- Thuyết minh: {f'{duration:.2f}s ({audio_name})' if duration > 0 else 'Chưa có'}")
        
        # Tab 6 (Result)
        export_info = meta.get('exports', {})
        final_video = export_info.get('final_video_path', '')
        if final_video and os.path.exists(final_video):
            self.lbl_video_result_status.configure(text=f"Đã dựng thành công: {os.path.basename(final_video)}\nĐường dẫn: {final_video}", text_color="#10b981")
            self.btn_open_export_dir.configure(state="normal")
        else:
            self.lbl_video_result_status.configure(text="Video chưa được dựng hoặc file xuất đã bị xóa.", text_color="#e2e8f0")
            self.btn_open_export_dir.configure(state="disabled")
            
        # Caption & Hashtags suggestions
        self.caption_display_box.set(script_info.get('caption', ''))
        self.hashtags_display_box.set(script_info.get('hashtags', ''))

        # Load ideas for Idea Engine tab if exists
        saved_ideas = load_ideas(folders["root"])
        if saved_ideas and saved_ideas.get("ideas"):
            self.current_ideas_data = saved_ideas
            ideas = saved_ideas.get("ideas", [])
            self.idea_stats_lbl.configure(text=f"Tổng: {len(ideas)} angle (đã lưu)")
            self._render_idea_cards(ideas)
        else:
            # Clear ideas display
            for widget in self.idea_cards_frame.winfo_children():
                widget.destroy()
            self.idea_checkboxes.clear()
            ctk.CTkLabel(
                self.idea_cards_frame,
                text="Chưa có ý tưởng nào.\nNhấn '🤖 AI Tạo Ý Tưởng' để bắt đầu.",
                font=ctk.CTkFont(size=13), text_color="#4b5563"
            ).pack(pady=60)
            self.idea_stats_lbl.configure(text="Chưa có ý tưởng nào")

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
            messagebox.showerror("Thiếu thông tin", "Vui lòng nhập tên dự án / sản phẩm để tạo dự án.")
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
        messagebox.showinfo("Thành công", f"Đã khởi tạo / lưu dự án thành công tại:\nprojects/{slug}")

    # --- ACTION 2: KEYWORDS ---

    def create_quick_project(self, project_name=None):
        if not project_name:
            dialog = ctk.CTkInputDialog(text="Nhập tên dự án / sản phẩm mới:", title="Tạo dự án mới")
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
        self.tab_flow1.set("📋 Sản phẩm")
        messagebox.showinfo("Thành công", f"Đã tạo / mở dự án:\n{path}")

    def open_auto_pipeline_dialog(self):
        """Mở cửa sổ nhập link Shopee/TikTok và chạy quy trình tự động."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("🚀 Quy Trình Tạo Dự Án Tự Động 1-Click")
        dialog.geometry("600x480")
        dialog.transient(self) # hiển thị trên cửa sổ cha
        dialog.grab_set() # chiếm quyền tương tác
        
        # Center the dialog window
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Layout
        ctk.CTkLabel(
            dialog,
            text="🚀 Tự Động Hóa Toàn Diện 1-Click",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#10b981"
        ).pack(pady=(15, 5))
        
        ctk.CTkLabel(
            dialog,
            text="Nhập link sản phẩm TikTok Video hoặc Shopee Product để AI tự động\ncào thông tin, tải phôi, cắt clip dọc và viết kịch bản.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        ).pack(pady=(0, 15))
        
        # URL Entry
        url_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        url_frame.pack(fill="x", padx=25, pady=5)
        
        ctk.CTkLabel(url_frame, text="Đường dẫn (URL):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=2)
        in_url = ctk.CTkEntry(url_frame, placeholder_text="Dán link Shopee hoặc video TikTok vào đây...", height=35)
        in_url.pack(fill="x")
        
        # Run Button
        btn_run = ctk.CTkButton(
            dialog,
            text="🚀 Bắt Đầu Quy Trình Tự Động",
            height=38,
            fg_color=COLORS["success"],
            hover_color="#16a34a",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_run.pack(fill="x", padx=25, pady=15)
        
        # Console Log area
        ctk.CTkLabel(dialog, text="Tiến trình đang chạy:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=25, pady=(5, 2))
        log_box = ConsoleView(dialog, height=200)
        log_box.pack(fill="both", expand=True, padx=25, pady=(0, 15))
        
        def start_run():
            url = in_url.get().strip()
            if not url:
                messagebox.showerror("Thiếu đường dẫn", "Vui lòng dán link Shopee hoặc TikTok trước.")
                return
                
            if not config.GEMINI_API_KEY:
                messagebox.showerror("Lỗi cấu hình", "Chưa cấu hình GEMINI_API_KEY ở tab Cấu hình.")
                return
                
            btn_run.configure(state="disabled", text="⏳ Đang chạy tự động...")
            in_url.configure(state="disabled")
            
            def run_thread():
                try:
                    def gui_log(msg):
                        dialog.after(0, lambda: log_box.log(msg))
                        
                    result = pc.run_auto_pipeline(url, log_callback=gui_log)
                    dialog.after(0, lambda: finish_run(result))
                except Exception as ex:
                    dialog.after(0, lambda: log_box.log(f"[x] Lỗi nghiêm trọng: {ex}"))
                    dialog.after(0, lambda: btn_run.configure(state="normal", text="🚀 Chạy Lại Quy Trình"))
                    
            threading.Thread(target=run_thread, daemon=True).start()
            
        def finish_run(result):
            btn_run.configure(state="normal", text="🚀 Bắt Đầu Quy Trình Tự Động")
            in_url.configure(state="normal")
            
            slug = result.get("project_slug") or result.get("slug")
            if slug:
                self.active_project_slug = slug
                self.load_project_list()
                self.load_project_details(slug)

            if "error" in result:
                log_box.log("\n" + "="*50)
                log_box.log(f"[x] 🛑 CẢNH BÁO: QUY TRÌNH DỪNG LẠI DO LỖI THIẾU TÀI NGUYÊN PHÔI")
                log_box.log(f"[x] {result['error']}")
                log_box.log("[*] Dự án đã được tạo sẵn. Bạn có thể tự dán ảnh/video sản phẩm thủ công vào thư mục Phoi/ rồi bấm cắt clip.")
                log_box.log("="*50)
                btn_run.configure(state="normal", text="🔄 Thử Lại Quy Trình Tự Động")
                return
                
            prod_name = result.get("product_name", "Dự án mới")
            messagebox.showinfo(
                "Hoàn thành xuất sắc",
                f"Đã hoàn thành toàn bộ quy trình tự động cho sản phẩm:\n'{prod_name}'!\n\n"
                f"• Dự án mới đã được khởi tạo và kích hoạt.\n"
                f"• Tài nguyên phôi đã được cào & cắt dọc 9:16.\n"
                f"• Kịch bản quảng cáo mới đã được sinh xong.\n\n"
                f"Bây giờ bạn có thể nạp audio thuyết minh ở tab Audio hoặc bấm dựng ở tab Dựng video."
            )
            
            # Switch to Editor tab and close dialog
            self.switch_flow(1)
            self.tab_flow1.set("🎬 Dựng video")
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
        normalized = normalized.replace("Tiếng Việt:", "\n").replace("Tiếng Anh:", "\n").replace("Tiếng Trung:", "\n")
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
            messagebox.showerror("Lỗi", "Vui lòng chọn hoặc tạo dự án trước khi mở rộng key.")
            return

        h1_query = self.in_h1_query.get().strip()
        if h1_query:
            # Hướng 1: NLP expansion from entry box
            if not config.GEMINI_API_KEY:
                messagebox.showerror("Lỗi Gemini", "Chưa nhập Gemini API Key. Hãy cấu hình ở tab Cấu hình.")
                return
            self.btn_gen_kw.configure(state="disabled", text="AI đang mở rộng...")
            def run():
                try:
                    res = nlp_expand_keywords(h1_query)
                    kws = res.get("vi", []) + res.get("en", []) + res.get("zh", [])
                    def update_gui():
                        self.btn_gen_kw.configure(state="normal", text="AI mở rộng key")
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
                        
                        messagebox.showinfo("Thành công", f"AI đã phân tích thực thể:\n- Sản phẩm: {res.get('entities', {}).get('product', '')}\n- Tính năng: {res.get('entities', {}).get('features', '')}\n- Màu sắc: {res.get('entities', {}).get('color', '')}\n\nĐã mở rộng và cập nhật từ khóa!")
                    self.after(0, update_gui)
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Lỗi API", f"Lỗi mở rộng từ khóa: {e}"))
                    self.after(0, lambda: self.btn_gen_kw.configure(state="normal", text="AI mở rộng key"))
            threading.Thread(target=run, daemon=True).start()
        else:
            # Default behavior (manual keywords text list expansion)
            manual_keywords = self.sync_manual_keywords_to_metadata(save=True)
            if not manual_keywords:
                messagebox.showwarning("Thiếu key", "Vui lòng nhập tên sản phẩm ở ô trên hoặc ít nhất một từ khóa trước khi dùng AI mở rộng.")
                return
            if not config.GEMINI_API_KEY:
                messagebox.showerror("Lỗi Gemini", "Chưa nhập Gemini API Key. Hãy cấu hình ở tab Cấu hình.")
                return
            self.btn_gen_kw.configure(state="disabled", text="AI đang mở rộng...")
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
        self.btn_gen_kw.configure(state="normal", text="AI mở rộng key")
        if "error" in kws:
            messagebox.showerror("Lỗi API", kws["error"])
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
        messagebox.showinfo("Thành công", "Đã mở rộng key tìm phôi bằng AI.")

    def run_manual_translation_zh(self):
        manual_keywords = self.sync_manual_keywords_to_metadata(save=True)
        text_to_translate = "\n".join(manual_keywords)
        if not text_to_translate:
            messagebox.showwarning("Trống", "Vui lòng nhập key cần dịch trong ô key tìm phôi.")
            return
            
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lỗi Gemini", "Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập khóa API ở tab Cấu hình.")
            return
            
        self.btn_run_translate_zh.configure(state="disabled", text="Đang dịch...")
        self.in_translate_zh_result.set("Đang dịch bằng AI...")
        
        def run():
            from core.keyword_generator import translate_to_zh
            res = translate_to_zh(text_to_translate)
            
            def update_gui():
                self.btn_run_translate_zh.configure(state="normal", text="Dịch key")
                self.in_translate_zh_result.set(res)
                if not res.startswith("Lỗi"):
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
            title="Chọn Supplier Feed File", 
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
            messagebox.showerror("Lỗi", "Vui lòng chọn hoặc tạo dự án trước.")
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
            messagebox.showerror("Lỗi nhập liệu", "Số prompt AI, số clip/key và thời lượng phải là số nguyên.")
            return

        if ai_video_prompt_count <= 0 or ai_video_clips_per_prompt <= 0 or ai_video_duration <= 0:
            messagebox.showerror("Lỗi nhập liệu", "Số prompt AI, số clip/key và thời lượng phải lớn hơn 0.")
            return
        
        cookie_sel = self.browser_cookies_combo.get()
        pasted_text = self.in_urls_paste.get("1.0", "end-1c").strip()
        urls_to_download = [u.strip() for u in pasted_text.split('\n') if u.strip()]
        
        # Verify inputs based on active tab
        h1_query = self.in_h1_query.get().strip()
        h2_url = self.in_h2_url.get().strip()
        
        if active_tab == "Hướng 2: URL sản phẩm":
            if not h2_url:
                messagebox.showerror("Lỗi", "Vui lòng nhập đường dẫn URL sản phẩm ở Hướng 2.")
                return
        else:
            # Hướng 1: check keywords
            manual_search_terms = self.sync_manual_keywords_to_metadata(save=True)
            if not h1_query and not manual_search_terms and not (use_urls and urls_to_download) and not (use_feed and self.supplier_feed_file):
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập tên sản phẩm hoặc từ khóa tìm kiếm ở Hướng 1.")
                return
                
        # Disable buttons
        self.btn_run_downloaders.configure(state="disabled", text="Đang tải phôi...")
        self.downloads_console.clear()
        
        def run():
            log = self.downloads_console.log
            log("[*] Khởi động tiến trình cào và tải phôi thông minh...")
            
            folders = self.project_manager.get_project_folders(self.active_project_slug)
            materials_dir = folders["materials"]
            os.makedirs(materials_dir, exist_ok=True)
            
            search_terms = []
            
            # --- DIRECTION 2: URL Parsing ---
            if active_tab == "Hướng 2: URL sản phẩm":
                log(f"\n--- HƯỚNG 2: PHÂN TÍCH URL SẢN PHẨM ---")
                log(f"[*] URL đích: {h2_url}")
                
                shop_id, item_id = parse_shopee_url(h2_url)
                if shop_id and item_id:
                    # Shopee API extraction with browser cookies support
                    details = fetch_shopee_product_details(shop_id, item_id, browser_cookies=cookie_sel, log_callback=log)
                    if details:
                        log(f"[+] Lấy thông tin sản phẩm thành công: '{details['title']}'")
                        
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            # Direct Image Download (parallelized)
                            if use_prod_images:
                                log("[*] Tải bộ sưu tập ảnh sản phẩm gốc Shopee (Song song)...")
                                for i, img_hash in enumerate(details["images"][:4]):
                                    img_url = f"https://down-vn.img.susercontent.com/file/{img_hash}"
                                    target_path = os.path.join(materials_dir, f"shopee_og_img_{item_id}_{i+1}.jpg")
                                    executor.submit(download_direct, img_url, target_path, log)
                                    
                            # Direct Video Download (parallelized)
                            if use_shopee:
                                log("[*] Tải video mô tả gốc Shopee (Song song)...")
                                for i, video in enumerate(details["video_info_list"][:2]):
                                    video_url = video.get("default_format", {}).get("url") or video.get("url") or f"https://cvf.shopee.vn/{video.get('video_id')}"
                                    if video_url:
                                        executor.submit(download_video_clean, video_url, materials_dir, f"shopee_og_vid_{item_id}", cookie_sel, True, 120, log)
                                    
                        # AI keyword extraction from page details
                        log("[*] AI đang bóc tách từ khóa cốt lõi từ tiêu đề và mô tả...")
                        kw_result = extract_keywords_from_product_page(details["title"], details["description"])
                        search_terms = self._unique_keywords(kw_result.get("vi", []) + kw_result.get("en", []) + kw_result.get("zh", []))
                        log(f"[+] Từ khóa cốt lõi AI đề xuất để cào MXH: {', '.join(search_terms)}")
                    else:
                        log("[!] Không thể cào chi tiết Shopee API. Chuyển sang cào HTML dự phòng...")
                        shop_id = None
                
                # Fallback parser for non-Shopee or blocked Shopee API
                if not shop_id:
                    try:
                        headers = {"User-Agent": "Mozilla/5.0"}
                        res = requests.get(h2_url, headers=headers, timeout=15)
                        if res.status_code == 200:
                            title_match = re.search(r'<title>(.*?)</title>', res.text, re.IGNORECASE)
                            title = title_match.group(1).strip() if title_match else "Sản phẩm mới"
                            log(f"[+] Lấy tiêu đề trang web: '{title}'")
                            kw_result = extract_keywords_from_product_page(title, "")
                            search_terms = self._unique_keywords(kw_result.get("vi", []) + kw_result.get("en", []) + kw_result.get("zh", []))
                            log(f"[+] Từ khóa AI cốt lõi: {', '.join(search_terms)}")
                    except Exception as e:
                        log(f"[x] Lỗi cào generic page: {e}")
                        
            # --- DIRECTION 1: Direct Keyword ---
            else:
                log(f"\n--- HƯỚNG 1: TÊN SẢN PHẨM & TỪ KHÓA ---")
                # Auto NLP expansion if keyword textbox is empty
                manual_search_terms = self.sync_manual_keywords_to_metadata(save=True)
                if h1_query and not manual_search_terms:
                    log(f"[*] Ô Từ khóa trống. Tự động chạy AI NLP mở rộng từ khóa cho: '{h1_query}'...")
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
                log("[!] Cảnh báo: Không có từ khóa tìm kiếm. Bỏ qua cào tìm kiếm.")
            else:
                log(f"\n[*] Danh sách từ khóa tìm kiếm: {search_terms[:5]}")
                
                from concurrent.futures import ThreadPoolExecutor
                futures = []
                
                with ThreadPoolExecutor(max_workers=3) as executor:
                    # 1. Product HD Image Search (Google/Shopee query search)
                    if use_prod_images and active_tab == "Hướng 1: Tên sản phẩm":
                        log("\n--- BẮT ĐẦU TẢI ẢNH SẢN PHẨM HD (Google & Shopee Search) (Song song) ---")
                        for term in search_terms[:2]:
                            futures.append(executor.submit(search_and_download_product_images, term, materials_dir, 4, log))
                            
                    # 2. Shopee Search Crawler
                    if use_shopee and active_tab == "Hướng 1: Tên sản phẩm":
                        log("\n--- BẮT ĐẦU CÀO VIDEO TÌM KIẾM SHOPEE (Song song) ---")
                        for term in search_terms[:2]:
                            futures.append(executor.submit(
                                search_and_download_shopee, term, materials_dir, 3, False, True, cookie_sel, log
                            ))

                    # 3. DuckDuckGo Scrape for TikTok & Douyin
                    if use_social:
                        log("\n--- BẮT ĐẦU CÀO TÌM KIẾM TIKTOK & DOUYIN (DuckDuckGo Scrape) (Song song) ---")
                        for term in search_terms[:2]:
                            # A. TikTok
                            def crawl_tiktok(t=term):
                                log(f"[*] Tìm video review trên TikTok cho: '{t}'...")
                                tiktok_links = search_duckduckgo_urls(t, "tiktok.com", limit=2, log_callback=log)
                                for link in tiktok_links:
                                    download_video_clean(link, materials_dir, prefix="social_tiktok", browser_cookies=cookie_sel, log_callback=log)
                            
                            # B. Douyin
                            def crawl_douyin(t=term):
                                log(f"[*] Tìm video review trên Douyin cho: '{t}'...")
                                douyin_links = search_duckduckgo_urls(t, "douyin.com", limit=2, log_callback=log)
                                for link in douyin_links:
                                    download_video_clean(link, materials_dir, prefix="social_douyin", browser_cookies=cookie_sel, log_callback=log)
                                    
                            futures.append(executor.submit(crawl_tiktok))
                            futures.append(executor.submit(crawl_douyin))
                            
                        # 4. Fallback/Standard Social Crawler (Bilibili / Youtube Shorts via standard yt-dlp search)
                        log("\n--- BẮT ĐẦU CÀO YT SHORTS & BILIBILI (yt-dlp Search) (Song song) ---")
                        for term in search_terms[:2]:
                            futures.append(executor.submit(
                                search_and_download_social, term, materials_dir, 2, 60, True, cookie_sel, log
                            ))

                    # 5. Pexels Download
                    if use_pexels:
                        if not config.PEXELS_API_KEY:
                            log("[!] Bỏ qua Pexels: Chưa cấu hình API Key.")
                        else:
                            log("\n--- BẮT ĐẦU TẢI PEXELS STOCK (Song song) ---")
                            for term in search_terms[:2]:
                                futures.append(executor.submit(search_and_download_pexels, term, materials_dir, 3, log))
                                
                    # 6. Pixabay Download
                    if use_pixabay:
                        if not config.PIXABAY_API_KEY:
                            log("[!] Bỏ qua Pixabay: Chưa cấu hình API Key.")
                        else:
                            log("\n--- BẮT ĐẦU TẢI PIXABAY STOCK (Song song) ---")
                            for term in search_terms[:2]:
                                futures.append(executor.submit(search_and_download_pixabay, term, materials_dir, 3, log))

                # Chờ tất cả tiến trình cào và tải phôi hoàn thành
                for fut in futures:
                    try:
                        fut.result()
                    except Exception as err:
                        log(f"[!] Lỗi trong tiến trình cào phôi: {err}")

                            
            # 7. Paste URLs Download
            if use_urls and urls_to_download:
                log("\n--- BẮT ĐẦU TẢI DANH SÁCH URL TỰ DÁN ---")
                download_url_list(urls_to_download, materials_dir, browser_cookies=cookie_sel, log_callback=log)
                
            # 8. Supplier Feed Download
            if use_feed and self.supplier_feed_file:
                log(f"\n--- BẮT ĐẦU TẢI FILE FEED: {os.path.basename(self.supplier_feed_file)} ---")
                run_supplier_feed_provider(
                    self.supplier_feed_file, 
                    self.active_project_meta.get("product_name", "product"),
                    materials_dir,
                    keywords_list=search_terms,
                    log_callback=log
                )

            # 9. AI Video Generation
            if use_ai_video:
                log(f"\n--- BẮT ĐẦU TẠO PHÔI AI VIDEO: {ai_video_provider} ---")
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
                    log(f"[+] Đã tải {len(generated)} video AI vào thư mục phôi.")
                else:
                    log("[*] Đã tạo kịch bản prompt pack để dán thủ công.")

            # --- POST-PROCESSING FLOW: OpenCV Filter & Audio/Video Splitting ---
            log("\n--- BẮT ĐẦU TIỀN XỬ LÝ & LỌC CHẤT LƯỢNG PHÔI ---")
            video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}
            for f in os.listdir(materials_dir):
                ext = os.path.splitext(f)[1].lower()
                if ext in video_extensions:
                    filepath = os.path.abspath(os.path.join(materials_dir, f))
                    try:
                        self._post_process_downloaded_file(filepath, folders, log)
                    except Exception as e:
                        log(f"[!] Lỗi hậu kỳ tệp {f}: {e}")
                        
            log("\n[+] Hoàn thành toàn bộ lượt cào và tải phôi thành công!")
            self.after(0, self.finish_downloading_materials)
            
        threading.Thread(target=run, daemon=True).start()

    def finish_downloading_materials(self):
        self.btn_run_downloaders.configure(state="normal", text="Bắt Đầu Tải Phôi")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Hoàn thành", "Đã hoàn thành lượt tải phôi video.")

    # --- ACTION 2.3: CLIP CUTTING & ANALYSIS ---

    def start_clip_cutting(self):
        if not self.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn hoặc tạo dự án trước.")
            return
            
        try:
            clip_dur = float(self.in_clip_duration.get().strip())
            skip_start = float(self.in_skip_start.get().strip())
            max_clips = int(self.in_max_clips.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi nhập liệu", "Độ dài clip, bỏ qua đầu video và số clip tối đa phải là số hợp lệ.")
            return
            
        if clip_dur <= 0 or skip_start < 0 or max_clips <= 0:
            messagebox.showerror("Lỗi nhập liệu", "Các thông số cấu hình phải lớn hơn 0.")
            return
            
        # Disable button
        self.btn_run_clipper.configure(state="disabled", text="Đang xử lý cắt clip...")
        self.clip_cutting_console.clear()
        
        # Checkboxes
        export_vert = self.cb_vertical_crop_var.get() == "on"
        mute_audio = self.cb_mute_clip_var.get() == "on"
        analyze_qual = self.cb_quality_analysis_var.get() == "on"
        reject_bad = self.cb_discard_bad_clips_var.get() == "on"
        
        def run():
            self.clip_cutting_console.log("[*] Khởi động tiến trình tự động cắt clip phôi dọc...")
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
        self.btn_run_clipper.configure(state="normal", text="Bắt Đầu Cắt Clip Phôi")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Thành công", f"Đã hoàn thành cắt clip phôi! Đã xử lý thêm {count} clip.")

    def open_clips_dir(self):
        if not self.active_project_slug:
            return
        folders = self.project_manager.get_project_folders(self.active_project_slug)
        clips_path = folders["clips"]
        if os.path.exists(clips_path):
            try:
                os.startfile(clips_path)
            except Exception as e:
                messagebox.showerror("Lỗi mở thư mục", f"Không mở được thư mục: {e}")

    def refresh_clip_statistics(self):
        if not self.active_project_slug:
            self.lbl_total_clips.configure(text="Tổng clip đã tạo: 0")
            self.lbl_good_clips.configure(text="Clip tốt (>=70): 0")
            self.lbl_okay_clips.configure(text="Clip tạm ổn (>=45): 0")
            self.lbl_rejected_clips.configure(text="Clip bị loại (<45): 0")
            self.lbl_failed_clips.configure(text="Clip lỗi: 0")
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
        
        self.lbl_total_clips.configure(text=f"Tổng clip đã tạo: {total}")
        self.lbl_good_clips.configure(text=f"Clip tốt (>=70): {good}")
        self.lbl_okay_clips.configure(text=f"Clip tạm ổn (>=45): {okay}")
        self.lbl_rejected_clips.configure(text=f"Clip bị loại (<45): {rejected}")
        self.lbl_failed_clips.configure(text=f"Clip lỗi: {failed}")

    # --- ACTION 2.4: STORYBOARD AI GENERATION ---

    

    # --- ACTION 3: SCRIPTS ---
    
    def generate_project_script(self):
        if not self.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn hoặc lưu dự án trước.")
            return
            
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lỗi Gemini", "Chưa nhập Gemini API Key. Hãy cấu hình ở tab Cấu hình.")
            return
            
        style = self.script_style_combo.get()
        selected_learned = self.script_learned_combo.get()
        
        # Load reference style if selected
        ref_style = None
        if selected_learned != "Không áp dụng" and hasattr(self, "kb_slug_mapping"):
            slug = self.kb_slug_mapping.get(selected_learned)
            if slug:
                ref_style = kb.get_learned_detail(slug)
                
        self.btn_gen_script.configure(state="disabled", text="Đang sinh kịch bản...")
        
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
        self.btn_gen_script.configure(state="normal", text="Viết kịch bản mới (AI Gemini)")
        messagebox.showerror("Lỗi sinh kịch bản", err_msg)

    def finish_script_generation(self):
        self.btn_gen_script.configure(state="normal", text="Viết kịch bản mới (AI Gemini)")
        self.load_project_details(self.active_project_slug)
        messagebox.showinfo("Thành công", "Kịch bản quảng cáo đã được sinh thành công!")

    def copy_script_to_clipboard(self):
        script_text = self.script_display_box.get().strip()
        if script_text:
            self.clipboard_clear()
            self.clipboard_append(script_text)
            messagebox.showinfo("Sao chép", "Đã sao chép kịch bản voiceover vào clipboard!")
        else:
            messagebox.showwarning("Trống", "Không có kịch bản để sao chép.")

    # --- ACTION 4: AUDIO IMPORT ---
    
    def import_voice_audio(self):
        if not self.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn dự án trước.")
            return
            
        file_path = filedialog.askopenfilename(title="Chọn File Thuyết Minh ElevenLabs", filetypes=[("Audio files", "*.mp3")])
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
            messagebox.showinfo("Thành công", f"Đã nạp file thuyết minh. Độ dài đo được: {duration:.2f} giây.")
        except Exception as e:

            messagebox.showerror("Lỗi", f"Không nạp được file thuyết minh: {e}")



    # ==================== MERGED TAB: HỌC & DUYỆT ====================

    def build_tab_learn_and_review(self):
        """Merged tab: Học hỏi từ video mẫu + Hàng đợi duyệt bài học (Bố cục Tabview cột giữa)."""
        tab = self.tab_flow2.tab("📚 Học & Duyệt")
        self._learn_review_tab_instance = LearnReviewTab(tab, self)

    # ==================== MERGED TAB: CÀI ĐẶT ====================

    def build_tab_settings_merged(self):

        """Merged tab: Biên dịch Prompt + Cấu hình hệ thống."""

        tab = self.tab_flow2.tab("🛠️ Cài Đặt")

        self._settings_tab_instance = SettingsTab(tab, self)

    def save_settings(self):
        try:
            gemini_key = self.sett_gemini_key.get().strip()
            pexels_key = self.sett_pexels_key.get().strip()
            pixabay_key = self.sett_pixabay_key.get().strip()
            ffmpeg_path = self.sett_ffmpeg_path.get().strip()
            projects_root = self.sett_projects_root.get().strip()
            
            ai_video_keys = {
                "GROK_API_KEY": self.sett_grok_key.get().strip() if hasattr(self, "sett_grok_key") else "",
                "RUNWAY_API_KEY": self.sett_runway_key.get().strip() if hasattr(self, "sett_runway_key") else "",
                "PIKA_API_KEY": self.sett_pika_key.get().strip() if hasattr(self, "sett_pika_key") else "",
                "KREA_API_KEY": self.sett_krea_key.get().strip() if hasattr(self, "sett_krea_key") else "",
                "LEONARDO_API_KEY": self.sett_leonardo_key.get().strip() if hasattr(self, "sett_leonardo_key") else "",
                "AI_VIDEO_CUSTOM_API_KEY": self.sett_ai_custom_key.get().strip() if hasattr(self, "sett_ai_custom_key") else "",
                "AI_VIDEO_CUSTOM_ENDPOINT": self.sett_ai_custom_endpoint.get().strip() if hasattr(self, "sett_ai_custom_endpoint") else "",
                "GROQ_API_KEY": self.sett_groq_key.get().strip() if hasattr(self, "sett_groq_key") else "",
                "CEREBRAS_API_KEY": self.sett_cerebras_key.get().strip() if hasattr(self, "sett_cerebras_key") else "",
                "MISTRAL_API_KEY": self.sett_mistral_key.get().strip() if hasattr(self, "sett_mistral_key") else "",
                "OPENROUTER_API_KEY": self.sett_openrouter_key.get().strip() if hasattr(self, "sett_openrouter_key") else "",
                "TOGETHER_API_KEY": self.sett_together_key.get().strip() if hasattr(self, "sett_together_key") else "",
                "ELEVENLABS_API_KEY": self.sett_elevenlabs_key.get().strip() if hasattr(self, "sett_elevenlabs_key") else "",
            }

            import config
            config.save_config(
                gemini_key=gemini_key,
                gemini_model=config.GEMINI_MODEL,
                pexels_key=pexels_key,
                pixabay_key=pixabay_key,
                ffmpeg_path=ffmpeg_path,
                projects_root=projects_root,
                ai_video_keys=ai_video_keys
            )
            
            # Reload projects
            self.load_project_list()
            
            # Re-run environment checks
            self.check_ffmpeg()
            self.check_gemini_silent()
            
            # Reset AI router singleton so it picks up new keys
            try:
                from core import ai_router as _ar
                _ar._router = None
            except Exception:
                pass
            
            # Refresh router status display
            self.after(200, self._refresh_router_status)
            
            messagebox.showinfo("Thành công", "Đã lưu cấu hình mới thành công vào tệp .env!")
        except Exception as e:
            messagebox.showerror("Lỗi lưu file", f"Không lưu được cấu hình: {e}")





if __name__ == "__main__":

    # Kiểm tra cấu hình và cảnh báo nếu thiếu

    config.verify_config()

    app = HermesTikTokVideoFactoryApp()

    app.mainloop()

