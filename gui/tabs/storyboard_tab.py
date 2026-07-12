import os
import sys
import threading
from tkinter import messagebox, filedialog
from pathlib import Path
import customtkinter as ctk

# Ensure correct pathing for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import config
from gui.theme import COLORS, secondary_button_kwargs
from gui.components import LabeledEntry, LabeledTextbox, ConsoleView
from core.storyboard_writer import save_storyboard_outputs
from core.prompt_engine import generate_prompts_from_storyboard
from core.file_manager import to_slug

class StoryboardTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance

        # Left Panel (options/config) and Right Panel (results/console)
        self.tab.grid_columnconfigure(0, weight=4)
        self.tab.grid_columnconfigure(1, weight=6)
        self.tab.grid_rowconfigure(0, weight=1)
        
        opt_scroll = ctk.CTkScrollableFrame(self.tab, fg_color="transparent")
        opt_scroll.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        right_frame = ctk.CTkFrame(self.tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        # Mode selector at the top
        lbl_mode = ctk.CTkLabel(opt_scroll, text="Chế độ Storyboard AI:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_mode.pack(anchor="w", pady=(2, 4))
        
        self.app.sb_mode_combo = ctk.CTkComboBox(
            opt_scroll, 
            values=["Tạo từ văn bản (Text)", "Trích xuất từ video mẫu"],
            command=self.on_sb_mode_changed,
            state="readonly",
            height=30
        )
        self.app.sb_mode_combo.pack(fill="x", pady=(0, 10))
        self.app.sb_mode_combo.set("Tạo từ văn bản (Text)")
        
        # --- FRAME 1: TEXT MODE ---
        self.app.sb_text_mode_frame = ctk.CTkFrame(opt_scroll, fg_color="transparent")
        self.app.sb_text_mode_frame.pack(fill="x", expand=True)
        
        lbl_info = ctk.CTkLabel(self.app.sb_text_mode_frame, text="Thông tin sản phẩm:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_info.pack(anchor="w", pady=(2, 4))
        
        self.app.sb_prod_name = LabeledEntry(self.app.sb_text_mode_frame, "Tên sản phẩm *", "Máy tăm nước cầm tay")
        self.app.sb_prod_name.pack(fill="x", pady=2)
        
        self.app.sb_prod_desc = LabeledTextbox(self.app.sb_text_mode_frame, "Mô tả sản phẩm", height=60)
        self.app.sb_prod_desc.pack(fill="x", pady=2)
        
        self.app.sb_prod_usp = LabeledEntry(self.app.sb_text_mode_frame, "Điểm bán hàng chính (USP)", "Ví dụ: Áp lực phun mạnh, pin trâu")
        self.app.sb_prod_usp.pack(fill="x", pady=2)
        
        self.app.sb_prod_pain = LabeledEntry(self.app.sb_text_mode_frame, "Nỗi đau khách hàng (Pain points)", "Ví dụ: Hay chảy máu nướu răng, dắt thức ăn")
        self.app.sb_prod_pain.pack(fill="x", pady=2)
        
        self.app.sb_prod_audience = LabeledEntry(self.app.sb_text_mode_frame, "Đối tượng người xem", "Ví dụ: Giới trẻ niềng răng, dân văn phòng")
        self.app.sb_prod_audience.pack(fill="x", pady=2)
        
        div = ctk.CTkFrame(self.app.sb_text_mode_frame, height=2, fg_color="#2d2d34")
        div.pack(fill="x", pady=10)
        
        lbl_dir = ctk.CTkLabel(self.app.sb_text_mode_frame, text="Định hướng video & AI Prompts:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_dir.pack(anchor="w", pady=(2, 4))
        
        self.app.sb_video_style = LabeledEntry(self.app.sb_text_mode_frame, "Phong cách video quảng cáo", "Ví dụ: TikTok review sản phẩm chân thật...")
        self.app.sb_video_style.pack(fill="x", pady=2)
        self.app.sb_video_style.set("TikTok review sản phẩm chân thật, quay cận cảnh thao tác tay, ánh sáng sáng sạch, nhịp nhanh")
        
        row_dur = ctk.CTkFrame(self.app.sb_text_mode_frame, fg_color="transparent")
        row_dur.pack(fill="x", pady=2)
        row_dur.grid_columnconfigure(0, weight=1)
        row_dur.grid_columnconfigure(1, weight=1)
        
        self.app.sb_duration = LabeledEntry(row_dur, "Thời lượng (giây)", "24")
        self.app.sb_duration.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.app.sb_duration.set("24")
        
        self.app.sb_scene_count = LabeledEntry(row_dur, "Số phân cảnh", "6")
        self.app.sb_scene_count.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.app.sb_scene_count.set("6")
        
        self.app.sb_background = LabeledEntry(self.app.sb_text_mode_frame, "Bối cảnh / Background mong muốn", "Ví dụ: Phòng tắm hiện đại, tối giản")
        self.app.sb_background.pack(fill="x", pady=2)
        self.app.sb_background.set("Phòng khách studio ấm áp, sạch sẽ")
        
        self.app.sb_product_image_note = LabeledEntry(self.app.sb_text_mode_frame, "Ghi chú ảnh sản phẩm tham chiếu", "Ví dụ: Màu trắng sứ, có logo chữ nổi")
        self.app.sb_product_image_note.pack(fill="x", pady=2)
        self.app.sb_product_image_note.set("Cận cảnh cầm trên tay, rõ chi tiết các nút bấm")
        
        self.app.sb_background_image_note = LabeledEntry(self.app.sb_text_mode_frame, "Ghi chú ảnh background tham chiếu", "Ví dụ: Kệ gỗ sồi sáng màu, cây xanh nhỏ")
        self.app.sb_background_image_note.pack(fill="x", pady=2)
        self.app.sb_background_image_note.set("Màu gỗ sáng, tối giản, có cây xanh nhòe mờ phía sau")
        
        lbl_target = ctk.CTkLabel(self.app.sb_text_mode_frame, text="Công cụ AI Video đích:", font=ctk.CTkFont(size=11))
        lbl_target.pack(anchor="w", pady=(5, 2))
        self.app.sb_prompt_target = ctk.CTkComboBox(
            self.app.sb_text_mode_frame, 
            values=["Google Labs / Veo", "ChatGPT image generation", "Gemini image/video", "Generic AI video prompt"],
            state="readonly",
            height=28
        )
        self.app.sb_prompt_target.pack(fill="x", pady=(0, 5))
        self.app.sb_prompt_target.set("Google Labs / Veo")
        
        # --- FRAME 2: VIDEO MODE ---
        self.app.sb_video_mode_frame = ctk.CTkFrame(opt_scroll, fg_color="transparent")
        
        lbl_vid_title = ctk.CTkLabel(self.app.sb_video_mode_frame, text="Phân tích video mẫu để trích xuất prompt:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_vid_title.pack(anchor="w", pady=(2, 4))
        
        row_sel_vid = ctk.CTkFrame(self.app.sb_video_mode_frame, fg_color="transparent")
        row_sel_vid.pack(fill="x", pady=2)
        row_sel_vid.grid_columnconfigure(0, weight=1)
        
        self.app.sb_sample_video_path = LabeledEntry(row_sel_vid, "Đường dẫn tệp video mẫu *", "Chọn file video từ máy tính...")
        self.app.sb_sample_video_path.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        btn_browse_vid = ctk.CTkButton(row_sel_vid, text="Chọn video", command=self.browse_sample_video, width=80, height=28)
        btn_browse_vid.grid(row=0, column=1, sticky="s", pady=(18, 0))
        
        lbl_vid_target = ctk.CTkLabel(self.app.sb_video_mode_frame, text="Công cụ AI Video đích nhắm tới:", font=ctk.CTkFont(size=11))
        lbl_vid_target.pack(anchor="w", pady=(10, 2))
        self.app.sb_video_prompt_target = ctk.CTkComboBox(
            self.app.sb_video_mode_frame, 
            values=["Google Labs / Veo", "Luma Dream Machine", "Runway Gen-3", "OpenAI Sora", "Generic AI video prompt"],
            state="readonly",
            height=28
        )
        self.app.sb_video_prompt_target.pack(fill="x", pady=(0, 5))
        self.app.sb_video_prompt_target.set("Google Labs / Veo")
        
        # Custom action entry
        lbl_custom_action = ctk.CTkLabel(self.app.sb_video_mode_frame, text="Mô tả hành động trong video (Tiếng Việt - Tùy chọn):", font=ctk.CTkFont(size=11))
        lbl_custom_action.pack(anchor="w", pady=(10, 2))
        self.app.sb_custom_action = ctk.CTkEntry(
            self.app.sb_video_mode_frame,
            placeholder_text="Ví dụ: tay cầm giá đỡ điện thoại gập lên xuống, xoay vòng...",
            height=28
        )
        self.app.sb_custom_action.pack(fill="x", pady=(0, 5))
        
        # Offline mode checkbox
        self.app.sb_offline_only = ctk.CTkCheckBox(
            self.app.sb_video_mode_frame,
            text="Chỉ phân tích ngoại tuyến (Không gọi Gemini API)",
            font=ctk.CTkFont(size=11)
        )
        self.app.sb_offline_only.pack(fill="x", pady=(8, 5))
        
        # Right Panel: Buttons, Preview, and Console
        row_btns = ctk.CTkFrame(right_frame, fg_color="transparent")
        row_btns.pack(fill="x", pady=(0, 5))
        
        self.app.btn_gen_sb = ctk.CTkButton(row_btns, text="Tạo storyboard", command=self.start_storyboard_generation, width=130, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.app.btn_gen_sb.pack(side="left", padx=4)
        
        self.app.btn_extract_prompt = ctk.CTkButton(row_btns, text="Trích xuất prompt", command=self.start_prompt_extraction, width=130, fg_color="#8b5cf6", hover_color="#7c3aed")
        
        self.app.btn_save_sb = ctk.CTkButton(row_btns, text="Lưu kết quả", command=self.save_storyboard, width=130, fg_color="#10b981", hover_color="#059669")
        self.app.btn_save_sb.pack(side="left", padx=4)
        
        self.app.btn_open_sb_dir = ctk.CTkButton(row_btns, text="Mở thư mục", command=self.open_storyboard_dir, width=110, **secondary_button_kwargs())
        self.app.btn_open_sb_dir.pack(side="left", padx=4)
        
        # Copy Buttons Row
        row_copy = ctk.CTkFrame(right_frame, fg_color="transparent")
        row_copy.pack(fill="x", pady=5)
        
        self.app.btn_copy_all_sb = ctk.CTkButton(row_copy, text="Copy toàn bộ kết quả", command=self.copy_all_storyboard, width=140, height=28, font=ctk.CTkFont(size=11))
        self.app.btn_copy_all_sb.pack(side="left", padx=3)
        
        self.app.btn_copy_img_p = ctk.CTkButton(row_copy, text="Copy prompt ảnh", command=self.copy_image_prompts, width=120, height=28, font=ctk.CTkFont(size=11))
        self.app.btn_copy_img_p.pack(side="left", padx=3)
        
        self.app.btn_copy_vid_p = ctk.CTkButton(row_copy, text="Copy prompt video", command=self.copy_video_prompts, width=120, height=28, font=ctk.CTkFont(size=11))
        self.app.btn_copy_vid_p.pack(side="left", padx=3)
 
        self.app.btn_export_prompts = ctk.CTkButton(
            row_copy, text="📤 Xuất Prompts Pack", command=self.export_prompts_from_storyboard,
            width=150, height=28, font=ctk.CTkFont(size=11),
            fg_color="#10b981", hover_color="#059669"
        )
        self.app.btn_export_prompts.pack(side="left", padx=3)
 
        # Markdown Preview area
        lbl_prev = ctk.CTkLabel(right_frame, text="Bản xem trước storyboard.md:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_prev.pack(anchor="w", pady=(5, 2))
        
        self.app.sb_preview_box = ctk.CTkTextbox(right_frame, height=260)
        self.app.sb_preview_box.pack(fill="both", expand=True, pady=(0, 10))
        self.app.sb_preview_box.configure(state="disabled")
        
        # Console Log
        lbl_console = ctk.CTkLabel(right_frame, text="Nhật ký Storyboard AI:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_console.pack(anchor="w", pady=(0, 2))
        
        self.app.storyboard_console = ConsoleView(right_frame, height=100)
        self.app.storyboard_console.pack(fill="x")

    def start_storyboard_generation(self):
        if not config.GEMINI_API_KEY:
            messagebox.showerror("Lỗi Gemini", "Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập khóa API ở tab Cấu hình.")
            return
            
        prod_name = self.app.sb_prod_name.get().strip()
        if not prod_name:
            messagebox.showerror("Thiếu thông tin", "Vui lòng nhập Tên sản phẩm để tạo Storyboard.")
            return
            
        try:
            duration = int(self.app.sb_duration.get().strip())
            scenes = int(self.app.sb_scene_count.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi nhập liệu", "Thời lượng và số phân cảnh phải là số nguyên hợp lệ.")
            return
            
        if duration <= 0 or scenes <= 0:
            messagebox.showerror("Lỗi nhập liệu", "Thời lượng và số phân cảnh phải lớn hơn 0.")
            return
            
        # Disable button & clear previous state
        self.app.btn_gen_sb.configure(state="disabled", text="Đang tạo bằng Gemini...")
        self.app.storyboard_console.clear()
        
        self.app.sb_preview_box.configure(state="normal")
        self.app.sb_preview_box.delete("1.0", "end")
        self.app.sb_preview_box.configure(state="disabled")
        
        self.app.latest_storyboard_data = None
        
        # Read fields
        desc = self.app.sb_prod_desc.get().strip()
        usp = self.app.sb_prod_usp.get().strip()
        pain = self.app.sb_prod_pain.get().strip()
        aud = self.app.sb_prod_audience.get().strip()
        style = self.app.sb_video_style.get().strip()
        bg = self.app.sb_background.get().strip()
        img_note = self.app.sb_product_image_note.get().strip()
        bg_note = self.app.sb_background_image_note.get().strip()
        target = self.app.sb_prompt_target.get()
        
        def run():
            self.app.storyboard_console.log("[*] Đang gửi yêu cầu sinh phân cảnh (Storyboard AI) đến Gemini...")
            
            from core.storyboard_generator import generate_storyboard
            res = generate_storyboard(
                prod_name, desc, usp, aud, pain,
                style, bg, img_note, bg_note,
                duration_seconds=duration,
                scene_count=scenes,
                prompt_target=target
            )
            
            self.app.after(0, lambda: self.finish_storyboard_generation(res))
            
        threading.Thread(target=run, daemon=True).start()

    def finish_storyboard_generation(self, result):
        self.app.btn_gen_sb.configure(state="normal", text="Tạo storyboard")
        
        if "error" in result:
            self.app.storyboard_console.log(f"[x] Lỗi: {result['error']}")
            messagebox.showerror("Lỗi API", result["error"])
            return
            
        self.app.latest_storyboard_data = result
        self.app.storyboard_console.log("[+] Tạo Storyboard AI thành công!")
        
        # Format and display in preview text box
        title = result.get("title", "Storyboard AI")
        concept = result.get("concept_summary", "")
        dur = result.get("video_duration", 24)
        sc = result.get("scene_count", 6)
        hooks = result.get("hook_options", [])
        ctas = result.get("cta_options", [])
        
        md = f"# Storyboard AI: {title}\n\n"
        md += f"## Tổng quan ý tưởng\n{concept}\n"
        md += f"- **Thời lượng**: {dur} giây | **Số phân cảnh**: {sc} cảnh\n\n"
        
        md += "## Hook đề xuất\n"
        for idx, h in enumerate(hooks):
            md += f"{idx + 1}. {h}\n"
        md += "\n"
        
        md += "## CTA đề xuất\n"
        for idx, c in enumerate(ctas):
            md += f"{idx + 1}. {c}\n"
        md += "\n"
        
        md += "## Phân cảnh chi tiết\n\n"
        for s in result.get("scenes", []):
            md += f"### Scene {s.get('scene_number', 1)} | {s.get('time_range', '')} | {s.get('scene_purpose', '')}\n"
            md += f"* **Mô tả hình ảnh**: {s.get('visual_description', '')}\n"
            md += f"* **Hành động**: {s.get('action_description', '')}\n"
            md += f"* **Góc máy/Chuyển động**: {s.get('camera_angle', '')} | {s.get('camera_movement', '')}\n"
            md += f"* **Ánh sáng/Background**: {s.get('lighting', '')} | {s.get('background', '')}\n"
            md += f"* **Tiêu điểm sản phẩm**: {s.get('product_focus', '')}\n"
            md += f"* **Voice**: {s.get('voiceover_line', '')}\n"
            md += f"* **Text**: {s.get('on_screen_text', '')}\n"
            md += f"* **Prompt ảnh EN**: {s.get('image_prompt_en', '')}\n"
            md += f"* **Prompt video EN**: {s.get('video_prompt_en', '')}\n\n"
            
        self.app.sb_preview_box.configure(state="normal")
        self.app.sb_preview_box.delete("1.0", "end")
        self.app.sb_preview_box.insert("end", md)
        self.app.sb_preview_box.configure(state="disabled")

    def save_storyboard(self):
        mode = self.app.sb_mode_combo.get()
        
        if mode == "Trích xuất từ video mẫu":
            if not hasattr(self.app, "latest_extracted_prompt_data") or not self.app.latest_extracted_prompt_data:
                messagebox.showerror("Trống", "Vui lòng trích xuất prompt từ video thành công trước khi lưu.")
                return
                
            video_path = self.app.sb_sample_video_path.get().strip()
            if not video_path:
                messagebox.showerror("Lỗi", "Đường dẫn video trống.")
                return
                
            video_name = os.path.basename(video_path)
            video_basename = os.path.splitext(video_name)[0]
            
            if self.app.active_project_slug:
                folders = self.app.project_manager.get_project_folders(self.app.active_project_slug)
                output_dir = os.path.join(folders["root"], "storyboard")
                proj_info = f"dự án: {self.app.active_project_slug}"
            else:
                slug = to_slug(self.app.sb_prod_name.get() or "video_prompt")
                output_dir = os.path.abspath(os.path.join(self.app.project_manager.get_projects_root(), "..", "storyboard_reports", slug))
                proj_info = f"báo cáo ngoài: {slug}"
                
            try:
                os.makedirs(output_dir, exist_ok=True)
                output_file = os.path.join(output_dir, f"{video_basename}_prompt.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(self.app.latest_extracted_prompt_data)
                
                self.app.storyboard_console.log(f"[+] Đã lưu prompt trích xuất thành công ({proj_info}) tại: {output_file}")
                messagebox.showinfo("Thành công", f"Đã lưu thành công tệp prompt tại:\n{output_file}")
            except Exception as e:
                self.app.storyboard_console.log(f"[x] Lỗi lưu Prompt: {e}")
                messagebox.showerror("Lỗi lưu file", f"Không thể lưu tệp prompt: {e}")
            return
            
        if not hasattr(self.app, "latest_storyboard_data") or not self.app.latest_storyboard_data:
            messagebox.showerror("Trống", "Vui lòng tạo Storyboard thành công trước khi lưu.")
            return
            
        if self.app.active_project_slug:
            folders = self.app.project_manager.get_project_folders(self.app.active_project_slug)
            output_dir = os.path.join(folders["root"], "storyboard")
            proj_info = f"dự án: {self.app.active_project_slug}"
        else:
            slug = to_slug(self.app.sb_prod_name.get())
            output_dir = os.path.abspath(os.path.join(self.app.project_manager.get_projects_root(), "..", "storyboard_reports", slug))
            proj_info = f"báo cáo ngoài: {slug}"
            
        try:
            paths = save_storyboard_outputs(self.app.latest_storyboard_data, output_dir)
            self.app.storyboard_console.log(f"[+] Đã lưu Storyboard thành công ({proj_info}) tại: {output_dir}")
            messagebox.showinfo("Thành công", f"Đã lưu thành công 4 file (storyboard.md, storyboard.json, image_prompts.txt, video_prompts.txt) tại:\n{output_dir}")
        except Exception as e:
            self.app.storyboard_console.log(f"[x] Lỗi lưu Storyboard: {e}")
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu các tệp storyboard: {e}")

    def open_storyboard_dir(self):
        mode = self.app.sb_mode_combo.get()
        
        if self.app.active_project_slug:
            folders = self.app.project_manager.get_project_folders(self.app.active_project_slug)
            output_dir = os.path.join(folders["root"], "storyboard")
        else:
            if mode == "Trích xuất từ video mẫu":
                slug = to_slug(self.app.sb_prod_name.get() or "video_prompt")
            else:
                slug = to_slug(self.app.sb_prod_name.get())
            output_dir = os.path.abspath(os.path.join(self.app.project_manager.get_projects_root(), "..", "storyboard_reports", slug))
            
        if os.path.exists(output_dir):
            try:
                os.startfile(output_dir)
            except Exception as e:
                messagebox.showerror("Lỗi mở thư mục", f"Không mở được thư mục: {e}")
        else:
            messagebox.showwarning("Không tồn tại", "Thư mục chưa được khởi tạo. Vui lòng bấm lưu kết quả trước.")

    def copy_all_storyboard(self):
        text = self.app.sb_preview_box.get("1.0", "end-1c").strip()
        if text:
            self.app.clipboard_clear()
            self.app.clipboard_append(text)
            messagebox.showinfo("Copy", "Đã copy toàn bộ kịch bản phân cảnh (Markdown) vào Clipboard!")
        else:
            messagebox.showwarning("Trống", "Không có kịch bản để copy.")

    def copy_image_prompts(self):
        if not hasattr(self.app, "latest_storyboard_data") or not self.app.latest_storyboard_data:
            messagebox.showwarning("Trống", "Chưa có dữ liệu storyboard để copy.")
            return
            
        prompts = []
        for s in self.app.latest_storyboard_data.get("scenes", []):
            num = s.get("scene_number", 1)
            en_prompt = s.get("image_prompt_en", "")
            neg_prompt = s.get("negative_prompt", "")
            prompts.append(f"--- SCENE {num} IMAGE PROMPT ---\n{en_prompt}\nNegative Prompt: {neg_prompt}")
            
        text = "\n\n".join(prompts)
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        messagebox.showinfo("Copy", "Đã copy danh sách prompt hình ảnh tiếng Anh vào Clipboard!")

    def copy_video_prompts(self):
        if not hasattr(self.app, "latest_storyboard_data") or not self.app.latest_storyboard_data:
            messagebox.showwarning("Trống", "Chưa có dữ liệu storyboard để copy.")
            return
            
        prompts = []
        for s in self.app.latest_storyboard_data.get("scenes", []):
            num = s.get("scene_number", 1)
            en_prompt = s.get("video_prompt_en", "")
            neg_prompt = s.get("negative_prompt", "")
            prompts.append(f"--- SCENE {num} VIDEO PROMPT ---\n{en_prompt}\nNegative Prompt: {neg_prompt}")
            
        text = "\n\n".join(prompts)
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        messagebox.showinfo("Copy", "Đã copy danh sách prompt video tiếng Anh vào Clipboard!")

    def on_sb_mode_changed(self, choice):
        if choice == "Tạo từ văn bản (Text)":
            self.app.sb_video_mode_frame.pack_forget()
            self.app.sb_text_mode_frame.pack(fill="x", expand=True)
            self.app.btn_extract_prompt.pack_forget()
            self.app.btn_gen_sb.pack(side="left", padx=4)
            self.app.btn_copy_img_p.configure(state="normal")
            self.app.btn_copy_vid_p.configure(state="normal")
        else:
            self.app.sb_text_mode_frame.pack_forget()
            self.app.sb_video_mode_frame.pack(fill="x", expand=True)
            self.app.btn_gen_sb.pack_forget()
            self.app.btn_extract_prompt.pack(side="left", padx=4)
            self.app.btn_copy_img_p.configure(state="disabled")
            self.app.btn_copy_vid_p.configure(state="disabled")

    def browse_sample_video(self):
        path = filedialog.askopenfilename(
            title="Chọn video mẫu để phân tích",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All files", "*.*")]
        )
        if path:
            self.app.sb_sample_video_path.set(path)

    def start_prompt_extraction(self):
        offline_only = self.app.sb_offline_only.get()
        custom_action = self.app.sb_custom_action.get().strip()
        
        if not offline_only:
            api_key = getattr(config, "GEMINI_API_KEY", "")
            if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                messagebox.showerror("Lỗi Gemini", "Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập khóa API ở tab Cấu hình.")
                return
            
        video_path = self.app.sb_sample_video_path.get().strip()
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Lỗi", "Vui lòng chọn tệp video mẫu hợp lệ trước khi phân tích.")
            return
            
        self.app.btn_extract_prompt.configure(state="disabled", text="Đang phân tích...")
        self.app.storyboard_console.clear()
        
        self.app.sb_preview_box.configure(state="normal")
        self.app.sb_preview_box.delete("1.0", "end")
        self.app.sb_preview_box.configure(state="disabled")
        
        self.app.latest_extracted_prompt_data = None
        target = self.app.sb_video_prompt_target.get()
        
        def run():
            if offline_only:
                self.app.storyboard_console.log(f"[*] Bắt đầu phân tích ngoại tuyến video mẫu...")
            else:
                self.app.storyboard_console.log(f"[*] Bắt đầu tải video mẫu lên Gemini API...")
            from tools.video_analyser import analyze_video
            
            prompt_text = f"""
Bạn là một chuyên gia hàng đầu về AI Video Prompt Engineering.
Hãy xem kỹ video được tải lên ở trên, phân tích chi tiết và viết báo cáo bằng tiếng Việt:

1. **PHÂN TÍCH CHI TIẾT VIDEO MẪU**:
   - **Hành động & Diễn tiến (Action & Motion)**: Mô tả chi tiết hành động của tay, người hoặc vật thể trong video.
   - **Môi trường & Ngữ cảnh (Environment & Context)**: Mô tả bối cảnh, phông nền, các vật thể xung quanh, màu sắc chủ đạo.
   - **Ánh sáng (Lighting)**: Mô tả loại ánh sáng (soft, studio, bright sunlight, cinematic...) và hướng sáng.
   - **Góc máy & Chuyển động Camera (Camera work)**: Mô tả tiêu cự (close-up, medium, macro...), góc máy (top-down, eye-level...) và chuyển động (panning, zoom in, static...).
   - **Nhịp độ & Thời lượng (Pacing)**: Tóm tắt nhịp độ chuyển cảnh và tốc độ diễn tiến.

2. **PROMPT RE-CREATION (Dùng để sinh video tương tự)**:
   - Viết một **Video Prompt bằng tiếng Anh** chi tiết và chuyên nghiệp nhất tương thích tốt với công cụ '{target}' để người dùng sao chép trực tiếp vào các AI Video Generator để tạo ra một video có cùng bối cảnh, chất lượng và hành động tương tự.
   - Prompt tiếng Anh cần kết hợp các từ khóa chuyên nghiệp: "vertical 9:16 aspect ratio", "TikTok review style", "highly realistic", "high detail", "8k resolution".
   - Định dạng Prompt:
     ```text
     [Copy-ready English Prompt]
     ```

3. **NEGATIVE PROMPT (Từ khóa loại trừ)**:
   - Các từ khóa loại trừ lỗi hình ảnh: "no watermark, no logo, no distorted hands, no deformed product, no text artifacts, no blurry text, extra fingers, bad anatomy, deformed fingers, low quality, grainy".
"""
            
            def gui_log(msg):
                self.app.after(0, lambda m=msg: self.app.storyboard_console.log(m))
                
            res = analyze_video(
                video_path, 
                prompt_text=prompt_text, 
                log_callback=gui_log,
                offline_only=offline_only,
                custom_action=custom_action
            )
            self.app.after(0, lambda: self.finish_prompt_extraction(res, video_path))
            
        threading.Thread(target=run, daemon=True).start()

    def finish_prompt_extraction(self, result, video_path):
        self.app.btn_extract_prompt.configure(state="normal", text="Trích xuất prompt")
        
        if result.startswith("Lỗi"):
            self.app.storyboard_console.log(f"[x] Lỗi: {result}")
            messagebox.showerror("Lỗi trích xuất", result)
            return
            
        self.app.latest_extracted_prompt_data = result
        self.app.storyboard_console.log("[+] Trích xuất prompt thành công!")
        
        self.app.sb_preview_box.configure(state="normal")
        self.app.sb_preview_box.delete("1.0", "end")
        self.app.sb_preview_box.insert("end", result)
        self.app.sb_preview_box.configure(state="disabled")
        
        # Auto save if project is active
        if self.app.active_project_slug:
            self.app.save_storyboard()

    def export_prompts_from_storyboard(self):
        """Xuất prompts từ storyboard đã tạo (3 formats: .md / .txt / .json)."""
        if not hasattr(self.app, "latest_storyboard_data") or not self.app.latest_storyboard_data:
            messagebox.showwarning("Chưa có storyboard", "Vui lòng tạo Storyboard AI trước.")
            return
        if not self.app.active_project_slug:
            messagebox.showwarning("Chưa chọn dự án", "Vui lòng chọn dự án trước.")
            return

        folders = self.app.project_manager.get_project_folders(self.app.active_project_slug)
        meta = self.app.active_project_meta or {}
        product_name = meta.get("product_name", "")

        self.app.storyboard_console.log("[*] Đang xuất prompts pack (3 formats)...")

        def run():
            result = generate_prompts_from_storyboard(
                storyboard_data=self.app.latest_storyboard_data,
                product_name=product_name,
                output_dir=folders["root"],
            )
            self.app.after(0, lambda: self.finish_export_prompts(result))

        threading.Thread(target=run, daemon=True).start()

    def finish_export_prompts(self, result):
        """Xử lý sau khi xuất prompts xong."""
        if "error" in result:
            self.app.storyboard_console.log(f"[x] Lỗi: {result['error']}")
            messagebox.showerror("Lỗi", result["error"])
            return

        n = result.get("prompts_count", 0)
        prompts_dir = result.get("prompts_dir", "")
        self.app.storyboard_console.log(f"[+] Đã xuất {n} scene prompts!")
        self.app.storyboard_console.log(f"[+] 📝 MD: {os.path.basename(result.get('md_path', ''))}")
        self.app.storyboard_console.log(f"[+] 📄 TXT: {n} files riêng lẻ")
        self.app.storyboard_console.log(f"[+] 💾 JSON: {os.path.basename(result.get('json_path', ''))}")
        self.app.storyboard_console.log(f"[+] Thư mục: {prompts_dir}")

        ans = messagebox.askyesno(
            "Xuất thành công",
            f"Đã xuất {n} scene prompts ra 3 formats!\n\n"
            f"• prompts_pack.md — review tổng hợp\n"
            f"• P01_prompt.txt ... P{str(n).zfill(2)}_prompt.txt — copy vào AI tool\n"
            f"• prompts.json — quản lý version\n\n"
            f"Mở thư mục prompts?"
        )
        if ans and prompts_dir and os.path.exists(prompts_dir):
            try:
                os.startfile(prompts_dir)
            except Exception:
                pass
