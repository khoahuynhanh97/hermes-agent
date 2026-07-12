import os
import sys
import threading
from tkinter import messagebox
import customtkinter as ctk

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from gui.theme import COLORS, secondary_button_kwargs

class AudioGeneratorTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance

        self.tab.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(self.tab, text="Thuyết Minh AI (TTS) — Không cần ElevenLabs",
                           font=ctk.CTkFont(size=15, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(20, 6))

        # ── TTS AUTO SECTION ──────────────────────────────────────────────────
        tts_frame = ctk.CTkFrame(self.tab, fg_color="#1a2435", corner_radius=10,
                                 border_width=1, border_color="#334155")
        tts_frame.pack(fill="x", padx=20, pady=(6, 10))

        ctk.CTkLabel(tts_frame,
                     text="🎤  Tạo Giọng Đọc Tự Động (Edge TTS — Miễn Phí)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#7dd3fc").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(tts_frame,
                     text="Chọn giọng → Điều chỉnh tốc độ → Nhấn 'Tạo' → voice.mp3 sẵn sàng cho dựng video",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=14, pady=(0, 8))

        # Voice selector row
        voice_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        voice_row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(voice_row, text="Giọng đọc:",
                     font=ctk.CTkFont(size=12), width=100).pack(side="left")
        self.app.tts_voice_var = ctk.StringVar(value="HoaiMy (Nữ miền Bắc)")
        self.app.tts_voice_menu = ctk.CTkOptionMenu(
            voice_row,
            values=[
                "HoaiMy (Nữ miền Bắc)",
                "NamMinh (Nam miền Bắc)",
            ],
            variable=self.app.tts_voice_var,
            width=220,
        )
        self.app.tts_voice_menu.pack(side="left", padx=8)
        ctk.CTkLabel(voice_row, text="*Edge TTS miễn phí, không cần API key",
                     font=ctk.CTkFont(size=10), text_color="#4ade80").pack(side="left", padx=8)

        # Speed slider row
        speed_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        speed_row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(speed_row, text="Tốc độ:",
                     font=ctk.CTkFont(size=12), width=100).pack(side="left")
        self.app.tts_speed_var = ctk.DoubleVar(value=1.1)
        speed_slider = ctk.CTkSlider(speed_row, from_=0.7, to=1.5,
                                     variable=self.app.tts_speed_var, width=180,
                                     command=lambda v: self.app.tts_speed_lbl.configure(
                                         text=f"{v:.1f}x"))
        speed_slider.pack(side="left", padx=8)
        self.app.tts_speed_lbl = ctk.CTkLabel(speed_row, text="1.1x",
                                          font=ctk.CTkFont(size=12), width=45)
        self.app.tts_speed_lbl.pack(side="left")
        ctk.CTkLabel(speed_row, text="(0.7 = chậm, 1.0 = bình thường, 1.5 = nhanh)",
                     font=ctk.CTkFont(size=10), text_color="#64748b").pack(side="left", padx=6)

        # Script preview box
        ctk.CTkLabel(tts_frame, text="Nội dung thuyết minh (lấy tự động từ kịch bản hoặc nhập tay):",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=14, pady=(6, 2))
        self.app.tts_text_box = ctk.CTkTextbox(tts_frame, height=100, font=ctk.CTkFont(size=12))
        self.app.tts_text_box.pack(fill="x", padx=14, pady=(0, 6))
        self.app.tts_text_box.insert("1.0", "Nhập lời thuyết minh vào đây, hoặc bấm 'Lấy từ kịch bản' để tự động nạp...")

        # Buttons row
        tts_btn_row = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_btn_row.pack(fill="x", padx=14, pady=(4, 12))

        ctk.CTkButton(tts_btn_row, text="📝 Lấy từ Kịch bản",
                      command=self._tts_load_from_script,
                      height=32, width=160,
                      fg_color="#1e40af", hover_color="#1d4ed8").pack(side="left", padx=4)

        ctk.CTkButton(tts_btn_row, text="🎤 Tạo Giọng Đọc",
                      command=self._tts_generate,
                      height=32, width=160,
                      fg_color="#7c3aed", hover_color="#6d28d9").pack(side="left", padx=4)

        self.app.tts_status_lbl = ctk.CTkLabel(tts_btn_row, text="",
                                           font=ctk.CTkFont(size=11),
                                           text_color="#4ade80")
        self.app.tts_status_lbl.pack(side="left", padx=8)

        # TTS progress bar
        self.app.tts_progress = ctk.CTkProgressBar(tts_frame, height=6)
        self.app.tts_progress.pack(fill="x", padx=14, pady=(0, 10))
        self.app.tts_progress.set(0)

        # ── MANUAL IMPORT SECTION (kept for backward compat) ──────────────────────────
        ctk.CTkLabel(self.tab,
                     text="— Hoặc import file MP3 thủ công (ElevenLabs/CapCut/khác) —",
                     font=ctk.CTkFont(size=11), text_color="#475569").pack(pady=(8, 4))
        
        row_import = ctk.CTkFrame(self.tab, fg_color="transparent")
        row_import.pack(fill="x", padx=20, pady=8)
        
        self.app.btn_import_audio = ctk.CTkButton(row_import, text="Chọn & Import File MP3",
                                              command=self.app.import_voice_audio, height=35,
                                              fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.app.btn_import_audio.pack(side="left")
        
        self.app.lbl_audio_status = ctk.CTkLabel(row_import, text="Chưa nạp âm thanh (.mp3)",
                                             font=ctk.CTkFont(size=13, weight="bold"),
                                             text_color="#ef4444")
        self.app.lbl_audio_status.pack(side="left", padx=20)
        
        self.app.lbl_audio_duration = ctk.CTkLabel(self.tab,
                                               text="Độ dài âm thanh thuyết minh: Chưa đo",
                                               font=ctk.CTkFont(size=12))
        self.app.lbl_audio_duration.pack(anchor="w", padx=20, pady=5)

    def _tts_load_from_script(self):
        """Load voiceover text from project's voice_script.txt."""
        proj = self.app.get_current_project_folders()
        if not proj:
            return
        script_path = os.path.join(proj["scripts"], "voice_script.txt")
        if not os.path.exists(script_path):
            messagebox.showwarning("Không có kịch bản",
                                   "Chưa có voice_script.txt. Hãy tạo kịch bản trước.")
            return
        with open(script_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        self.app.tts_text_box.delete("1.0", "end")
        self.app.tts_text_box.insert("1.0", text)
        self.app.tts_status_lbl.configure(text="✓ Đã tải kịch bản")

    def _tts_generate(self):
        """Generate TTS voice file from text in tts_text_box."""
        text = self.app.tts_text_box.get("1.0", "end-1c").strip()
        if not text or "Nhập lời thuyết minh" in text:
            messagebox.showwarning("Thiếu nội dung",
                                   "Nhập hoặc tải kịch bản trước khi tạo giọng đọc.")
            return

        proj = self.app.get_current_project_folders()
        if not proj:
            messagebox.showerror("Lỗi", "Chưa chọn dự án. Hãy tạo hoặc chọn dự án trước.")
            return

        voice_map = {
            "HoaiMy (Nữ miền Bắc)": "HoaiMy",
            "NamMinh (Nam miền Bắc)": "NamMinh",
        }
        voice = voice_map.get(self.app.tts_voice_var.get(), "HoaiMy")
        speed = self.app.tts_speed_var.get()
        output_path = os.path.join(proj["audio"], "voice.mp3")

        self.app.tts_status_lbl.configure(text="⏳ Đang tạo giọng đọc...", text_color="#fbbf24")
        self.app.tts_progress.set(0.1)
        self.app.update()

        def run_tts():
            try:
                from tools.tts_engine import synthesize
                out = synthesize(text, voice=voice, speed=speed, output_path=output_path)
                size_kb = os.path.getsize(out) / 1024
                self.app.after(0, lambda: self._tts_done(out, size_kb))
            except Exception as e:
                self.app.after(0, lambda: self._tts_error(str(e)))

        threading.Thread(target=run_tts, daemon=True).start()

    def _tts_done(self, path, size_kb):
        self.app.tts_progress.set(1.0)
        self.app.tts_status_lbl.configure(
            text=f"✓ Đã tạo! ({size_kb:.0f} KB)",
            text_color="#4ade80")
        self.app.lbl_audio_status.configure(text="✓ voice.mp3 sẵn sàng (TTS)", text_color="#4ade80")
        from editor.audio_helper import get_audio_duration
        dur = get_audio_duration(path)
        self.app.lbl_audio_duration.configure(text=f"Độ dài âm thanh: {dur:.1f} giây")
        messagebox.showinfo("✅ TTS Hoàn Tất",
                             f"File voice.mp3 đã được tạo!\n{path}\n\n"
                             f"Kích thước: {size_kb:.0f} KB | Thời lượng: {dur:.1f}s\n"
                             f"Sẵn sàng để dựng video trong Tab 'Dựng video'.")

    def _tts_error(self, err):
        self.app.tts_progress.set(0)
        self.app.tts_status_lbl.configure(text=f"❌ Lỗi: {err[:50]}", text_color="#ef4444")
        messagebox.showerror("Lỗi TTS", f"Không thể tạo giọng đọc:\n{err}")
