import os
import sys
import customtkinter as ctk

# Ensure correct pathing for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from hermes.channels.gui.theme import COLORS, font, primary_button_kwargs, secondary_button_kwargs
from hermes.channels.gui.components import ConsoleView, LabeledEntry, LabeledTextbox, SectionHeader

class LearnReviewTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance

        self.tab.grid_columnconfigure(0, weight=3)
        self.tab.grid_columnconfigure(1, weight=3)
        self.tab.grid_columnconfigure(2, weight=4)
        self.tab.grid_rowconfigure(0, weight=1)

        # ===================== CỘT TRÁI: NHẬP & HỌC =====================
        left = ctk.CTkScrollableFrame(self.tab, fg_color="transparent", width=240)
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        # Header
        SectionHeader(left, title="Học Hỏi Từ Video", icon="🧠",
                      subtitle="Dán link TikTok/YouTube để AI phân tích").pack(fill="x", pady=(5, 12))

        # URL Input
        self.app.in_kb_url = LabeledEntry(left, "Link Video YouTube / TikTok / Douyin:", "Dán đường dẫn video mẫu...")
        self.app.in_kb_url.pack(fill="x", pady=4)

        ctk.CTkLabel(left, text="Danh mục/Thể loại học hỏi:", font=font(12, "bold")).pack(anchor="w", pady=(8, 2))
        self.app.kb_category_combo = ctk.CTkComboBox(
            left,
            values=["Review sản phẩm", "Tin tức / Công nghệ", "Kịch tính (Drama)",
                    "Chia sẻ kiến thức", "Đập hộp (Unboxing)", "Hài hước / Vlog", "Khác"],
            state="readonly", height=32
        )
        self.app.kb_category_combo.pack(fill="x", pady=(0, 12))
        self.app.kb_category_combo.set("Review sản phẩm")

        self.app.btn_kb_learn = ctk.CTkButton(
            left, text="🧠 Gửi Job Học Hỏi", command=self.app.start_knowledge_learning,
            height=36, fg_color=COLORS["success"], hover_color="#16a34a",
            font=font(12, "bold")
        )
        self.app.btn_kb_learn.pack(fill="x", pady=(5, 14))

        ctk.CTkFrame(left, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", pady=8)

        ctk.CTkLabel(left, text="Nhật ký tiến trình:", font=font(12, "bold")).pack(anchor="w", pady=(2, 2))
        self.app.kb_console = ConsoleView(left, height=180)
        self.app.kb_console.pack(fill="both", expand=True)

        # ===================== CỘT GIỮA: TAB HÀNG ĐỢI & BÀI HỌC ĐÃ DUYỆT =====================
        mid = ctk.CTkFrame(self.tab, fg_color="transparent")
        mid.grid(row=0, column=1, padx=5, pady=10, sticky="nsew")
        mid.grid_rowconfigure(0, weight=1)
        mid.grid_columnconfigure(0, weight=1)

        self.app.kb_tabview = ctk.CTkTabview(
            mid, 
            corner_radius=10, 
            fg_color=COLORS["surface_2"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"]
        )
        self.app.kb_tabview.grid(row=0, column=0, sticky="nsew")
        
        self.app.kb_tabview.add("📥 Hàng Đợi Duyệt")
        self.app.kb_tabview.add("📚 Bài Học Đã Duyệt")
        
        # 1. Tab hàng đợi duyệt
        tab_queue = self.app.kb_tabview.tab("📥 Hàng Đợi Duyệt")
        tab_queue.grid_columnconfigure(0, weight=1)
        tab_queue.grid_rowconfigure(1, weight=1)
        
        queue_header = ctk.CTkFrame(tab_queue, fg_color="transparent")
        queue_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        queue_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(queue_header, text="Đề xuất cần duyệt", font=font(12, "bold"), text_color=COLORS["muted"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(queue_header, text="↻", command=self.app.refresh_learning_reviews, width=30, height=26, **secondary_button_kwargs()).grid(row=0, column=1, sticky="e")
        
        self.app.learning_review_scroll = ctk.CTkScrollableFrame(tab_queue, fg_color="#121214", corner_radius=8)
        self.app.learning_review_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.app.learning_review_scroll.grid_columnconfigure(0, weight=1)
        
        # 2. Tab bài học đã duyệt
        tab_approved = self.app.kb_tabview.tab("📚 Bài Học Đã Duyệt")
        tab_approved.grid_columnconfigure(0, weight=1)
        tab_approved.grid_rowconfigure(1, weight=1)
        
        approved_header = ctk.CTkFrame(tab_approved, fg_color="transparent")
        approved_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        approved_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(approved_header, text="Bài học đã lưu trữ", font=font(12, "bold"), text_color=COLORS["muted"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(approved_header, text="↻", command=self.app.kb_refresh_list, width=30, height=26, **secondary_button_kwargs()).grid(row=0, column=1, sticky="e")
        
        self.app.kb_list_scroll = ctk.CTkScrollableFrame(tab_approved, fg_color="#121214", corner_radius=8)
        self.app.kb_list_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.app.kb_list_scroll.grid_columnconfigure(0, weight=1)

        # ===================== CỘT PHẢI: PREVIEW =====================
        right = ctk.CTkFrame(self.tab, fg_color=COLORS["surface_2"], corner_radius=10,
                             border_width=1, border_color=COLORS["border_soft"])
        right.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        prev_header = ctk.CTkFrame(right, fg_color="transparent")
        prev_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        prev_header.grid_columnconfigure(0, weight=1)
        self.app.lbl_preview_title = ctk.CTkLabel(prev_header, text="📄 Xem Chi Tiết Đề Xuất", font=font(14, "bold"), text_color=COLORS["text"])
        self.app.lbl_preview_title.grid(row=0, column=0, sticky="w")
        self.app.btn_approve_review = ctk.CTkButton(
            prev_header, text="✅ Duyệt & Lưu", width=110, height=28,
            command=self.app.approve_learning_review, **primary_button_kwargs()
        )
        self.app.btn_approve_review.grid(row=0, column=1, sticky="e", padx=(0, 6))
        self.app.btn_reject_review = ctk.CTkButton(
            prev_header, text="❌ Từ chối", width=85, height=28,
            command=self.app.reject_learning_review,
            fg_color=COLORS["danger_bg"], hover_color="#5b1f23",
            text_color="#fecaca", corner_radius=8, font=font(11, "bold")
        )
        self.app.btn_reject_review.grid(row=0, column=2, sticky="e")

        # Tab preview
        self.app.learning_review_tabs = ctk.CTkTabview(right, corner_radius=8, fg_color="#0d1117",
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"])
        self.app.learning_review_tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.app.review_textboxes = {}
        for tab_name in ["Tóm tắt", "Phân tích", "Setup", "Prompt"]:
            self.app.learning_review_tabs.add(tab_name)
            tf = self.app.learning_review_tabs.tab(tab_name)
            tf.grid_columnconfigure(0, weight=1)
            tf.grid_rowconfigure(0, weight=1)
            tb = ctk.CTkTextbox(tf, corner_radius=6, fg_color="#0d1117", text_color="#d8e2f0",
                                border_width=0, font=font(13))
            tb.grid(row=0, column=0, sticky="nsew")
            self.app.review_textboxes[tab_name] = tb

        # Also keep reference for md_actions
        self.app.kb_md_actions_frame = ctk.CTkFrame(right, fg_color="transparent")

        self.app.current_review_selection = None
        self.app.learning_review_items = {}
        self.app.review_card_frames = {}
        self.app.refresh_learning_reviews()
        self.app.kb_refresh_list()
