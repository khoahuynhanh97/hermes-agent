import os
import sys
import json
from pathlib import Path
from tkinter import messagebox, filedialog
import customtkinter as ctk

# Ensure correct pathing for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from gui.theme import COLORS, secondary_button_kwargs
from gui.components import LabeledEntry, LabeledTextbox, ConsoleView
from core.agent_jobs import DEFAULT_TASKS

class AgentJobsTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance

        self.tab.grid_columnconfigure(0, weight=4)
        self.tab.grid_columnconfigure(1, weight=6)
        self.tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(self.tab, fg_color="transparent")
        left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        right = ctk.CTkFrame(self.tab, fg_color="transparent")
        right.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Agent Jobs Manager", font=ctk.CTkFont(size=16, weight="bold"), text_color="#60a5fa").pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(left, text="Tạo hàng đợi tác vụ cho Antigravity/Codex hoặc Worker tự động.", font=ctk.CTkFont(size=11), text_color="#94a3b8", justify="left").pack(anchor="w", pady=(0, 12))

        self.app.agent_source_box = LabeledTextbox(left, "TikTok link / video path", height=80)
        self.app.agent_source_box.pack(fill="x", pady=5)

        ctk.CTkButton(left, text="Chọn video local", command=self.agent_select_video, height=30, **secondary_button_kwargs()).pack(fill="x", pady=(0, 10))

        self.app.agent_target_mode = ctk.CTkComboBox(left, values=["Create new project", "Append to active/existing project"], state="readonly")
        self.app.agent_target_mode.pack(fill="x", pady=5)
        self.app.agent_target_mode.set("Create new project")

        ctk.CTkLabel(left, text="Engine", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 4))
        self.app.agent_engine = ctk.CTkComboBox(left, values=["ai_studio", "html_video", "mixed", "capcut", "upgrade_audit"], state="readonly")
        self.app.agent_engine.pack(fill="x", pady=5)
        self.app.agent_engine.set("ai_studio")

        self.app.agent_new_project_name = LabeledEntry(left, "Tên dự án mới (tùy chọn)", "Bỏ trống để hệ thống tự đặt tên")
        self.app.agent_new_project_name.pack(fill="x", pady=5)

        ctk.CTkLabel(left, text="Dự án hiện có", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 4))
        self.app.agent_project_combo = ctk.CTkComboBox(left, values=["No project"], state="readonly")
        self.app.agent_project_combo.pack(fill="x", pady=5)

        row = ctk.CTkFrame(left, fg_color="transparent")
        row.pack(fill="x", pady=(2, 10))
        ctk.CTkButton(row, text="Làm mới dự án", command=self.agent_refresh_projects, height=28, **secondary_button_kwargs()).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(row, text="Dùng dự án hiện tại", command=self.agent_use_active_project, height=28, **secondary_button_kwargs()).pack(side="left", fill="x", expand=True, padx=(4, 0))

        ctk.CTkLabel(left, text="Danh sách Tác vụ (Tasks)", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(8, 4))
        self.app.agent_task_vars = {}
        task_labels = {
            "analyze_video": "Phân tích nội dung video mẫu",
            "write_script": "Soạn kịch bản review / bán hàng",
            "write_image_prompts": "Tạo prompt hình ảnh 9:16",
            "write_voiceover": "Tạo văn bản thuyết minh sạch",
            "write_capcut_plan": "Tạo kế hoạch dựng video CapCut",
        }
        for task in DEFAULT_TASKS:
            var = ctk.BooleanVar(value=True)
            self.app.agent_task_vars[task] = var
            ctk.CTkCheckBox(left, text=task_labels.get(task, task), variable=var).pack(anchor="w", pady=2)

        self.app.agent_duration = LabeledEntry(left, "Thời lượng mục tiêu (giây)", "45")
        self.app.agent_duration.pack(fill="x", pady=(10, 5))
        self.app.agent_duration.set("45")

        self.app.agent_notes = LabeledTextbox(left, "Ghi chú yêu cầu cho Worker", height=80)
        self.app.agent_notes.pack(fill="x", pady=5)

        ctk.CTkButton(left, text="🚀 Tạo Job cho Antigravity / Codex", command=self.agent_create_job, height=38, fg_color="#10b981", hover_color="#059669", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(12, 5))

        # Right side: ChatGPT / Gemini Style Live Monitor Tabview
        self.app.agent_right_tabview = ctk.CTkTabview(right, corner_radius=8)
        self.app.agent_right_tabview.grid(row=0, column=0, sticky="nsew")

        tab_monitor = self.app.agent_right_tabview.add("🤖 Tiến Trình Live (AI Monitor)")
        tab_logs = self.app.agent_right_tabview.add("📝 Worker Prompt & System Logs")

        # Configure Tab 1: Live Monitor
        tab_monitor.grid_columnconfigure(0, weight=1)
        tab_monitor.grid_rowconfigure(2, weight=1)

        # Job Selection & Status Header
        header_frame = ctk.CTkFrame(tab_monitor, fg_color="#1e1e24", corner_radius=6)
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        ctk.CTkLabel(header_frame, text="Chọn Job theo dõi:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 5), pady=8)
        self.app.agent_job_select_combo = ctk.CTkComboBox(header_frame, values=["Chưa có Job nào"], command=self.on_agent_job_selected, state="readonly", width=220)
        self.app.agent_job_select_combo.pack(side="left", padx=5, pady=8)

        self.app.agent_job_status_badge = ctk.CTkLabel(header_frame, text="READY", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#3b82f6", text_color="white", corner_radius=4, padx=8, pady=2)
        self.app.agent_job_status_badge.pack(side="right", padx=10, pady=8)

        # Progress bar
        self.app.agent_job_progressbar = ctk.CTkProgressBar(tab_monitor, height=8, corner_radius=4)
        self.app.agent_job_progressbar.grid(row=1, column=0, sticky="ew", padx=5, pady=(2, 8))
        self.app.agent_job_progressbar.set(0.0)

        # Task Checklist Frame (ChatGPT Thinking Style)
        self.app.agent_checklist_frame = ctk.CTkScrollableFrame(tab_monitor, height=140, fg_color="#141418", corner_radius=6)
        self.app.agent_checklist_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        
        # Artifact Output Viewer Section
        art_frame = ctk.CTkFrame(tab_monitor, fg_color="transparent")
        art_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=(5, 2))
        ctk.CTkLabel(art_frame, text="Xem Sản Phẩm Đầu Ra:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        
        self.app.agent_artifact_btns_frame = ctk.CTkFrame(art_frame, fg_color="transparent")
        self.app.agent_artifact_btns_frame.pack(fill="x", pady=2)

        self.app.agent_output_viewer = ctk.CTkTextbox(tab_monitor, height=180, corner_radius=6, border_width=1, border_color="#3a3a3a")
        self.app.agent_output_viewer.grid(row=4, column=0, sticky="ew", padx=5, pady=(0, 5))

        # Configure Tab 2: Logs & Worker Prompt
        tab_logs.grid_columnconfigure(0, weight=1)
        tab_logs.grid_rowconfigure(1, weight=1)
        tab_logs.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(tab_logs, text="Worker Prompt (Copy cho Antigravity/Codex):", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w", pady=(5, 2))
        self.app.agent_prompt_preview = ctk.CTkTextbox(tab_logs, height=160, corner_radius=6, border_width=1, border_color="#3a3a3a")
        self.app.agent_prompt_preview.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        ctk.CTkLabel(tab_logs, text="Hệ thống Nhật ký (System Logs):", font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, sticky="sw", pady=(0, 2))
        self.app.agent_jobs_console = ConsoleView(tab_logs, height=140)
        self.app.agent_jobs_console.grid(row=3, column=0, sticky="nsew")

        row_actions = ctk.CTkFrame(tab_logs, fg_color="transparent")
        row_actions.grid(row=4, column=0, sticky="ew", pady=(8, 5))
        ctk.CTkButton(row_actions, text="Làm mới danh sách", command=self.agent_refresh_jobs, height=30, **secondary_button_kwargs()).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(row_actions, text="Sao chép Worker Prompt", command=self.agent_copy_worker_prompt, height=30, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"]).pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.app.agent_project_display_to_slug = {}
        self.app.agent_jobs_cache = {}
        self.app.agent_selected_job_id = None

        self.agent_refresh_projects()
        self.agent_refresh_jobs()
        self.start_agent_jobs_auto_refresh()

    def agent_select_video(self):
        path = filedialog.askopenfilename(
            title="Choose video file",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"), ("All files", "*.*")]
        )
        if path:
            self.app.agent_source_box.set(path)

    def agent_refresh_projects(self):
        projects = self.app.project_manager.list_projects()
        self.app.agent_project_display_to_slug = {}
        values = []
        for project in projects:
            display = f"{project['name']} ({project['slug']})"
            self.app.agent_project_display_to_slug[display] = project["slug"]
            values.append(display)
        if not values:
            values = ["No project"]
        self.app.agent_project_combo.configure(values=values)
        if self.app.active_project_slug:
            for display, slug in self.app.agent_project_display_to_slug.items():
                if slug == self.app.active_project_slug:
                    self.app.agent_project_combo.set(display)
                    return
        self.app.agent_project_combo.set(values[0])

    def agent_use_active_project(self):
        if not self.app.active_project_slug:
            messagebox.showwarning("No active project", "Please load or create a project first.")
            return
        self.app.agent_target_mode.set("Append to active/existing project")
        self.agent_refresh_projects()

    def agent_create_job(self):
        source_value = self.app.agent_source_box.get().strip()
        if not source_value:
            messagebox.showwarning("Missing source", "Please paste a TikTok link or choose a local video.")
            return

        selected_tasks = [task for task, var in self.app.agent_task_vars.items() if var.get()]
        if not selected_tasks:
            messagebox.showwarning("Missing tasks", "Please choose at least one task.")
            return

        try:
            duration_seconds = int(self.app.agent_duration.get().strip() or "45")
        except ValueError:
            messagebox.showerror("Invalid duration", "Target duration must be a number.")
            return

        mode_label = self.app.agent_target_mode.get()
        target_mode = "append_existing" if mode_label.startswith("Append") else "create_new"
        target_slug = None
        if target_mode == "append_existing":
            display = self.app.agent_project_combo.get()
            target_slug = self.app.agent_project_display_to_slug.get(display)
            if not target_slug:
                messagebox.showwarning("Missing project", "Please choose an existing project.")
                return

        try:
            job = self.app.agent_job_manager.create_job(
                source_value=source_value,
                target_mode=target_mode,
                target_project_slug=target_slug,
                new_project_name=self.app.agent_new_project_name.get().strip(),
                tasks=selected_tasks,
                style={
                    "language": "vi",
                    "video_format": "vertical_tiktok",
                    "duration_seconds": duration_seconds,
                    "notes": self.app.agent_notes.get().strip(),
                },
                engine=self.app.agent_engine.get().strip() or "ai_studio",
            )
        except Exception as exc:
            messagebox.showerror("Create job failed", str(exc))
            return

        self.app.agent_jobs_console.log(f"[+] Created {job['job_id']}")
        self.app.agent_jobs_console.log(f"    Project: {job['target']['project_slug']}")
        self.app.agent_jobs_console.log(f"    Inbox: {job['paths']['job_file']}")
        self.app.agent_jobs_console.log(f"    Worker prompt: {job['paths']['worker_prompt']}")
        self.app.agent_jobs_console.log(f"    Manifest: {job['paths'].get('manifest_file', '')}")
        self.app.agent_prompt_preview.delete("1.0", "end")
        try:
            prompt_path = job["paths"].get("manifest_worker_prompt") or job["paths"]["worker_prompt"]
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.app.agent_prompt_preview.insert("1.0", f.read())
        except Exception:
            self.app.agent_prompt_preview.insert("1.0", job["paths"]["worker_prompt"])

        self.app.active_project_slug = job["target"]["project_slug"]
        self.app.load_project_list()
        self.app.load_project_details(self.app.active_project_slug)
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
            self.app.after(3000, _loop)
        self.app.after(3000, _loop)

    def agent_refresh_jobs(self, silent=False):
        if not hasattr(self.app, "agent_jobs_console"):
            return
        if not silent:
            self.app.agent_jobs_console.clear()
            self.app.agent_jobs_console.log(f"Jobs root: {self.app.agent_job_manager.jobs_root}")
        
        jobs = self.app.agent_job_manager.list_jobs(limit=30)
        combo_values = []
        self.app.agent_jobs_cache = {}

        if not jobs:
            if not silent:
                self.app.agent_jobs_console.log("No jobs yet.")
            self.app.agent_job_select_combo.configure(values=["Chưa có Job nào"])
            self.app.agent_job_select_combo.set("Chưa có Job nào")
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
            self.app.agent_jobs_cache[display_str] = job
            if not silent:
                self.app.agent_jobs_console.log(f"[{st.upper()}] {jid} | {engine or pslug} | {progress_text.strip()}")

        self.app.agent_job_select_combo.configure(values=combo_values)
        if not self.app.agent_selected_job_id or not any(self.app.agent_selected_job_id in v for v in combo_values):
            self.app.agent_job_select_combo.set(combo_values[0])
            self.on_agent_job_selected(combo_values[0])
        else:
            # Refresh current selected display
            for v in combo_values:
                if self.app.agent_selected_job_id in v:
                    self.app.agent_job_select_combo.set(v)
                    self.on_agent_job_selected(v)
                    break

    def on_agent_job_selected(self, choice=None):
        if not choice or choice == "Chưa có Job nào":
            return

        summary_info = self.app.agent_jobs_cache.get(choice)
        if not summary_info:
            return

        job_id = summary_info["job_id"]
        self.app.agent_selected_job_id = job_id

        manifest_view = None
        job_data = None
        try:
            manifest_view = self.app.agent_job_manager.load_manifest_job(job_id, sync=True)
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
                self.app.agent_prompt_preview.delete("1.0", "end")
                try:
                    self.app.agent_prompt_preview.insert("1.0", prompt_path.read_text(encoding="utf-8"))
                except Exception:
                    self.app.agent_prompt_preview.insert("1.0", str(prompt_path))
        else:
            # Legacy fallback for older .agent_jobs entries.
            for folder in [self.app.agent_job_manager.inbox_dir, self.app.agent_job_manager.processing_dir, self.app.agent_job_manager.outbox_dir, self.app.agent_job_manager.failed_dir]:
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
        self.app.agent_job_status_badge.configure(text=badge_text, fg_color=badge_color)

        existing_files = set()
        if output_dir.exists():
            existing_files = {p.name for p in output_dir.glob("*")}

        for child in self.app.agent_checklist_frame.winfo_children():
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
            row = ctk.CTkFrame(self.app.agent_checklist_frame, fg_color="transparent")
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
        self.app.agent_job_progressbar.set(progress_pct)

        for child in self.app.agent_artifact_btns_frame.winfo_children():
            child.destroy()

        if output_dir.exists():
            artifact_files = [item.get("name") for item in artifact_entries if item.get("name")]
            if not artifact_files:
                artifact_files = [p.name for p in output_dir.glob("*") if p.name != "job.json"]
            if artifact_files:
                for fname in artifact_files:
                    btn = ctk.CTkButton(
                        self.app.agent_artifact_btns_frame,
                        text=fname,
                        height=26,
                        fg_color="#2e2e38",
                        hover_color="#3b82f6",
                        font=ctk.CTkFont(size=11),
                        command=lambda f=fname, d=output_dir: self.load_agent_output_file(d / f),
                    )
                    btn.pack(side="left", padx=3, pady=2)
            else:
                ctk.CTkLabel(self.app.agent_artifact_btns_frame, text="Dang cho Worker tao artifact...", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=5)
        else:
            ctk.CTkLabel(self.app.agent_artifact_btns_frame, text="Chua co thu muc artifact.", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", padx=5)

    def load_agent_output_file(self, file_path):
        """Display content of selected output artifact file in viewer textbox."""
        self.app.agent_output_viewer.delete("1.0", "end")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.app.agent_output_viewer.insert("1.0", content)
        except Exception as e:
            self.app.agent_output_viewer.insert("1.0", f"Lỗi đọc file: {e}")

    def agent_copy_worker_prompt(self):
        text = self.app.agent_prompt_preview.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Empty prompt", "Create a job first, then copy the worker prompt.")
            return
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        messagebox.showinfo("Copied", "Worker prompt copied to clipboard.")
