import os
import sys
import threading
from tkinter import messagebox
import customtkinter as ctk

# Ensure correct pathing for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from hermes.runtime import config
from hermes.channels.gui.theme import COLORS, font, primary_button_kwargs, secondary_button_kwargs
from hermes.channels.gui.components import ConsoleView
from hermes.application.core.idea_engine import generate_ideas, save_ideas, save_selected_angles

class IdeaEngineTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance

        self.tab.grid_columnconfigure(0, weight=3)
        self.tab.grid_columnconfigure(1, weight=7)
        self.tab.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Controls ---
        left = ctk.CTkScrollableFrame(self.tab, fg_color="transparent", width=260)
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        ctk.CTkLabel(left, text="💡 Idea Engine", font=ctk.CTkFont(size=16, weight="bold"), text_color="#60a5fa").pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(left, text="AI sinh & chấm điểm angle video\nUser tick chọn để triển khai", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left").pack(anchor="w", pady=(0, 12))

        # Số ideas
        row_n = ctk.CTkFrame(left, fg_color="transparent")
        row_n.pack(fill="x", pady=4)
        ctk.CTkLabel(row_n, text="Số ý tưởng muốn AI tạo:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.app.idea_num_var = ctk.StringVar(value="15")
        ctk.CTkEntry(row_n, textvariable=self.app.idea_num_var, width=45, height=26).pack(side="right")

        # Generate button
        self.app.btn_gen_ideas = ctk.CTkButton(
            left, text="🤖 AI Tạo Ý Tưởng", command=self.start_idea_generation,
            height=36, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.app.btn_gen_ideas.pack(fill="x", pady=(8, 4))

        # Auto-select shortcuts
        ctk.CTkLabel(left, text="Chọn nhanh theo điểm cao:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(12, 4))
        row_auto = ctk.CTkFrame(left, fg_color="transparent")
        row_auto.pack(fill="x", pady=2)
        row_auto.grid_columnconfigure(0, weight=1)
        row_auto.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(row_auto, text="✅ Top 3", command=lambda: self.auto_select_top_n(3),
                      height=30, fg_color="#10b981", hover_color="#059669").grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkButton(row_auto, text="✅ Top 5", command=lambda: self.auto_select_top_n(5),
                      height=30, fg_color="#10b981", hover_color="#059669").grid(row=0, column=1, padx=(4, 0), sticky="ew")

        ctk.CTkButton(left, text="⬜ Bỏ chọn tất cả", command=self.deselect_all_ideas,
                      height=28, **secondary_button_kwargs()).pack(fill="x", pady=(4, 12))

        # Divider
        ctk.CTkFrame(left, height=1, fg_color="#2d2d34").pack(fill="x", pady=8)

        # Save selected
        self.app.btn_save_angles = ctk.CTkButton(
            left, text="💾 Lưu Angle Đã Chọn", command=self.save_selected_angles_action,
            height=36, fg_color="#8b5cf6", hover_color="#7c3aed",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.app.btn_save_angles.pack(fill="x", pady=4)

        self.app.btn_to_storyboard = ctk.CTkButton(
            left, text="📋 Mở Storyboard AI", command=lambda: (self.app.switch_flow(2), self.app.tab_flow2.set("🖼️ Storyboard")),
            height=32, **secondary_button_kwargs()
        )
        self.app.btn_to_storyboard.pack(fill="x", pady=4)

        # Stats label
        self.app.idea_stats_lbl = ctk.CTkLabel(left, text="Chưa có ý tưởng nào", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left")
        self.app.idea_stats_lbl.pack(anchor="w", pady=(12, 4))

        # Console
        ctk.CTkLabel(left, text="Nhật ký:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(8, 2))
        self.app.idea_console = ConsoleView(left, height=120)
        self.app.idea_console.pack(fill="x")

        # --- Right Panel: Idea Card List ---
        right = ctk.CTkFrame(self.tab, fg_color="transparent")
        right.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        row_hdr = ctk.CTkFrame(right, fg_color="transparent")
        row_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ctk.CTkLabel(row_hdr, text="Danh sách angle gợi ý từ AI (tick chọn để triển khai):", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.app.idea_selected_lbl = ctk.CTkLabel(row_hdr, text="Đã chọn: 0", font=ctk.CTkFont(size=12), text_color="#10b981")
        self.app.idea_selected_lbl.pack(side="right", padx=10)

        self.app.idea_cards_frame = ctk.CTkScrollableFrame(right, fg_color="#121214", corner_radius=8)
        self.app.idea_cards_frame.grid(row=1, column=0, sticky="nsew")
        self.app.idea_cards_frame.grid_columnconfigure(0, weight=1)

        self.app.idea_placeholder_lbl = ctk.CTkLabel(
            self.app.idea_cards_frame,
            text="Chưa có ý tưởng nào.\nNhấn '🤖 AI Tạo Ý Tưởng' để bắt đầu.",
            font=ctk.CTkFont(size=13), text_color="#4b5563"
        )
        self.app.idea_placeholder_lbl.pack(pady=60)

    # --- IDEA ENGINE ACTIONS ---

    def start_idea_generation(self):
        """Gọi Gemini AI tạo danh sách ideas."""
        if not self.app.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn hoặc tạo dự án trước.")
            return
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lỗi Gemini", "Chưa cấu hình GEMINI_API_KEY.")
            return

        try:
            num_ideas = int(self.app.idea_num_var.get().strip())
        except ValueError:
            num_ideas = 15

        meta = self.app.active_project_meta or {}
        self.app.btn_gen_ideas.configure(state="disabled", text="⏳ Đang tạo ý tưởng...")
        self.app.idea_console.clear()
        self.app.idea_console.log("[*] Đang gọi Gemini AI tạo angle ideas...")

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
            self.app.after(0, lambda: self.finish_idea_generation(result))

        threading.Thread(target=run, daemon=True).start()

    def finish_idea_generation(self, result):
        """Xử lý kết quả từ AI và render cards."""
        self.app.btn_gen_ideas.configure(state="normal", text="🤖 AI Tạo Ý Tưởng")

        if "error" in result:
            self.app.idea_console.log(f"[x] Lỗi: {result['error']}")
            messagebox.showerror("Lỗi API", result["error"])
            return

        ideas = result.get("ideas", [])
        if not ideas:
            self.app.idea_console.log("[!] AI không trả về ý tưởng nào.")
            return

        self.app.current_ideas_data = result

        # Save to project
        folders = self.app.project_manager.get_project_folders(self.app.active_project_slug)
        save_ideas(folders["root"], result)
        self.app.idea_console.log(f"[+] Tạo thành công {len(ideas)} ý tưởng. Đã lưu ideas.json")
        self.app.idea_stats_lbl.configure(text=f"Tổng: {len(ideas)} angle")

        self._render_idea_cards(ideas)

    def _render_idea_cards(self, ideas):
        """Render idea cards vào scrollable frame."""
        # Clear old cards
        for widget in self.app.idea_cards_frame.winfo_children():
            widget.destroy()
        self.app.idea_checkboxes.clear()

        if not ideas:
            ctk.CTkLabel(self.app.idea_cards_frame, text="Không có ý tưởng.", text_color="#4b5563").pack(pady=40)
            return

        # Sort by total_score desc
        ideas_sorted = sorted(ideas, key=lambda x: x.get("total_score", 0), reverse=True)

        STATUS_COLORS = {
            "Dễ": "#10b981",
            "Trung bình": "#f59e0b",
            "Khó": "#ef4444",
        }

        for idx, idea in enumerate(ideas_sorted):
            var = ctk.BooleanVar(value=False)
            self.app.idea_checkboxes.append((idea, var))

            # Card frame
            card = ctk.CTkFrame(self.app.idea_cards_frame, fg_color="#1e1e24", corner_radius=8)
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
                ctk.CTkLabel(content, text=f"📽 {flow}", font=ctk.CTkFont(size=10), text_color="#6b7280", wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(0, 4))

            # Scores row
            scores_row = ctk.CTkFrame(content, fg_color="transparent")
            scores_row.pack(fill="x", pady=(2, 0))

            score_defs = [
                ("🎬 AI Video", "ai_video_score"),
                ("📸 Demo", "demo_score"),
                ("💰 Sell", "sell_score"),
                ("♻️ Reuse", "reuse_score"),
                ("📱 TikTok", "tiktok_fit"),
                ("⭐ Total", "total_score"),
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
                ctk.CTkLabel(content, text=f"💡 {notes}", font=ctk.CTkFont(size=10), text_color="#6b7280", wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(2, 0))

        self._update_selected_count()

    def _update_selected_count(self):
        """Update the selected count label."""
        count = sum(1 for _, var in self.app.idea_checkboxes if var.get())
        self.app.idea_selected_lbl.configure(text=f"Đã chọn: {count}")

    def auto_select_top_n(self, n):
        """Chọn top N angles theo total_score."""
        # Deselect all first
        for _, var in self.app.idea_checkboxes:
            var.set(False)

        # Sort by total_score, select top N
        sorted_ideas = sorted(self.app.idea_checkboxes, key=lambda x: x[0].get("total_score", 0), reverse=True)
        for i, (idea, var) in enumerate(sorted_ideas):
            if i < n:
                var.set(True)

        self._update_selected_count()
        self.app.idea_console.log(f"[+] Đã tự động chọn Top {n} angle theo điểm cao nhất.")

    def deselect_all_ideas(self):
        """Bỏ chọn tất cả."""
        for _, var in self.app.idea_checkboxes:
            var.set(False)
        self._update_selected_count()

    def save_selected_angles_action(self):
        """Lưu các angle đã tick chọn vào selected_angles.json."""
        if not self.app.active_project_slug:
            messagebox.showerror("Lỗi", "Vui lòng chọn dự án trước.")
            return

        selected = [idea for idea, var in self.app.idea_checkboxes if var.get()]
        if not selected:
            messagebox.showwarning("Chưa chọn", "Chưa chọn angle nào để lưu. Tick chọn ít nhất 1 angle.")
            return

        folders = self.app.project_manager.get_project_folders(self.app.active_project_slug)
        path = save_selected_angles(folders["root"], selected)
        self.app.idea_console.log(f"[+] Đã lưu {len(selected)} angle vào selected_angles.json")
        messagebox.showinfo("Đã lưu", f"Đã lưu {len(selected)} angle được chọn.\nFile: {path}\n\nSau đó vào tab Storyboard AI để tạo storyboard cho từng angle.")
