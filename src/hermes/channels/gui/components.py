import customtkinter as ctk
from hermes.channels.gui.theme import COLORS, font, mono


class CollapsibleSection(ctk.CTkFrame):
    """
    Web-like collapsible section with a clickable header bar and expandable body.
    Usage:
        section = CollapsibleSection(parent, title="Name", icon="📋", subtitle="hint")
        # place widgets into section.body
        ctk.CTkLabel(section.body, text="Hello").pack()
    """
    def __init__(self, parent, title="Section", icon="", subtitle="", expanded=True, accent_color=None, **kwargs):
        bg = kwargs.pop("fg_color", COLORS["surface_2"])
        super().__init__(parent, fg_color=bg, corner_radius=10,
                         border_width=1, border_color=COLORS["border_soft"], **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._expanded = expanded
        self._accent = accent_color or COLORS["accent"]

        # Header
        self._header = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        self._header.grid(row=0, column=0, sticky="ew")
        self._header.grid_columnconfigure(1, weight=1)

        # Left accent bar
        ctk.CTkFrame(self._header, width=4, corner_radius=2, fg_color=self._accent
                     ).grid(row=0, column=0, padx=(10, 8), pady=10, sticky="ns")

        # Title block
        t_frame = ctk.CTkFrame(self._header, fg_color="transparent")
        t_frame.grid(row=0, column=1, sticky="ew", pady=8)
        title_text = f"{icon}  {title}" if icon else title
        self._title_lbl = ctk.CTkLabel(t_frame, text=title_text, font=font(13, "bold"),
                                       text_color=COLORS["text"], anchor="w")
        self._title_lbl.pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(t_frame, text=subtitle, font=font(10),
                         text_color=COLORS["subtle"], anchor="w").pack(anchor="w")

        # Chevron
        self._chevron = ctk.CTkLabel(self._header, text="▾" if expanded else "▸",
                                     font=font(14, "bold"), text_color=COLORS["muted"], width=30)
        self._chevron.grid(row=0, column=2, padx=(4, 12))

        # Separator
        self._sep = ctk.CTkFrame(self, height=1, fg_color=COLORS["border_soft"])
        self._sep.grid(row=1, column=0, sticky="ew", padx=12)

        # Body
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(8, 12))
        self.body.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        if not expanded:
            self.body.grid_remove()
            self._sep.grid_remove()

        for w in [self._header, self._title_lbl, self._chevron]:
            w.bind("<Button-1>", self._toggle)

    def _toggle(self, event=None):
        if self._expanded:
            self.body.grid_remove()
            self._sep.grid_remove()
            self._chevron.configure(text="▸")
        else:
            self.body.grid()
            self._sep.grid()
            self._chevron.configure(text="▾")
        self._expanded = not self._expanded

    def expand(self):
        if not self._expanded:
            self._toggle()

    def collapse(self):
        if self._expanded:
            self._toggle()


class SectionHeader(ctk.CTkFrame):
    """Simple titled header bar with optional right-side action buttons."""
    def __init__(self, parent, title="", icon="", subtitle="",
                 btn_text=None, btn_cmd=None, btn2_text=None, btn2_cmd=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)

        title_text = f"{icon}  {title}" if icon else title
        ctk.CTkLabel(row, text=title_text, font=font(15, "bold"),
                     text_color=COLORS["text"], anchor="w").grid(row=0, column=0, sticky="w")

        col = 1
        if btn2_text:
            ctk.CTkButton(row, text=btn2_text, command=btn2_cmd, height=26, width=90,
                          font=font(11, "bold"), fg_color=COLORS["control"],
                          hover_color=COLORS["control_hover"], text_color=COLORS["text"],
                          corner_radius=6).grid(row=0, column=col, padx=(4, 0))
            col += 1
        if btn_text:
            ctk.CTkButton(row, text=btn_text, command=btn_cmd, height=26, width=90,
                          font=font(11, "bold"), fg_color=COLORS["accent"],
                          hover_color=COLORS["accent_hover"], text_color="#051016",
                          corner_radius=6).grid(row=0, column=col, padx=(8, 0))

        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=font(10),
                         text_color=COLORS["subtle"], anchor="w").grid(row=1, column=0, sticky="w")

        ctk.CTkFrame(self, height=1, fg_color=COLORS["border_soft"]).grid(
            row=2, column=0, sticky="ew", pady=(6, 0))


class ConsoleView(ctk.CTkFrame):
    """A scrolling text console for showing real-time logs in the GUI."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLORS["surface"], corner_radius=8, border_width=1, border_color=COLORS["border_soft"], **kwargs)
        
        self.text_area = ctk.CTkTextbox(
            self, 
            corner_radius=8, 
            font=mono(11), 
            fg_color="#0d1117", 
            text_color="#b7c2d6",
            border_width=0
        )
        self.text_area.pack(fill="both", expand=True, padx=2, pady=2)
        self.text_area.configure(state="disabled")

    def log(self, message):
        """Appends a line to the console and auto-scrolls to the bottom."""
        self.text_area.configure(state="normal")
        self.text_area.insert("end", f"{message}\n")
        self.text_area.see("end")
        self.text_area.configure(state="disabled")
        self.update_idletasks()

    def clear(self):
        """Clears the console screen."""
        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        self.text_area.configure(state="disabled")
        self.update_idletasks()

class LabeledEntry(ctk.CTkFrame):
    """A helper widget combining a label and an entry field."""
    def __init__(self, parent, label_text, placeholder="", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        
        self.label = ctk.CTkLabel(
            self, 
            text=label_text, 
            font=font(12, "bold"), 
            text_color=COLORS["muted"],
            anchor="w"
        )
        self.label.pack(fill="x", pady=(0, 4))
        
        self.entry = ctk.CTkEntry(
            self, 
            placeholder_text=placeholder, 
            height=32, 
            corner_radius=8,
            fg_color=COLORS["surface_2"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["subtle"]
        )
        self.entry.pack(fill="x")

    def get(self):
        return self.entry.get()

    def set(self, val):
        self.entry.delete(0, "end")
        self.entry.insert(0, str(val))

class LabeledTextbox(ctk.CTkFrame):
    """A helper widget combining a label and a large textbox."""
    def __init__(self, parent, label_text, height=80, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        
        self.label = ctk.CTkLabel(
            self, 
            text=label_text, 
            font=font(12, "bold"), 
            text_color=COLORS["muted"],
            anchor="w"
        )
        self.label.pack(fill="x", pady=(0, 4))
        
        self.textbox = ctk.CTkTextbox(
            self, 
            height=height, 
            corner_radius=8, 
            border_width=1, 
            border_color=COLORS["border"],
            fg_color=COLORS["surface_2"],
            text_color=COLORS["text"]
        )
        self.textbox.pack(fill="both", expand=True)

    def get(self):
        return self.textbox.get("1.0", "end-1c")

    def set(self, val):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", str(val))

class StatusIndicator(ctk.CTkFrame):
    """A label that shows green (OK) or red (ERROR) based on dependency status."""
    def __init__(self, parent, label_name, initial_status="Chưa kiểm tra", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        
        self.name_label = ctk.CTkLabel(
            self, 
            text=label_name, 
            font=font(12, "bold"), 
            text_color=COLORS["muted"],
            anchor="w", 
            width=140
        )
        self.name_label.pack(side="left")
        
        self.status_label = ctk.CTkLabel(
            self, 
            text=initial_status, 
            font=font(11, "bold"), 
            text_color=COLORS["subtle"], 
            padx=8, 
            pady=2, 
            corner_radius=4,
            fg_color=COLORS["surface_3"]
        )
        self.status_label.pack(side="left", padx=10)

    def set_ok(self, text="SẴN SÀNG"):
        self.status_label.configure(
            text=text, 
            text_color=COLORS["success"], 
            fg_color=COLORS["success_bg"]
        )

    def set_error(self, text="LỖI / THIẾU"):
        self.status_label.configure(
            text=text, 
            text_color=COLORS["danger"], 
            fg_color=COLORS["danger_bg"]
        )

    def set_info(self, text):
        self.status_label.configure(
            text=text, 
            text_color=COLORS["accent"], 
            fg_color=COLORS["accent_soft"]
        )


class PromptStudioActionBar(ctk.CTkFrame):
    """
    Action bar containing buttons for Prompt Studio steps:
    - Edit (Chỉnh sửa)
    - Copy (Sao chép)
    - Regen (Tạo lại)
    - Next (Approve)
    """
    def __init__(self, parent, on_edit, on_copy, on_regen, on_next, next_label="Duyệt & Tiếp tục", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="equal")

        # Edit button
        self.btn_edit = ctk.CTkButton(
            self, text="📝 Chỉnh sửa", command=on_edit, height=36,
            font=font(11, "bold"), fg_color=COLORS["control"],
            hover_color=COLORS["control_hover"], text_color=COLORS["text"],
            corner_radius=8
        )
        self.btn_edit.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        # Copy button
        self.btn_copy = ctk.CTkButton(
            self, text="📋 Sao chép", command=on_copy, height=36,
            font=font(11, "bold"), fg_color=COLORS["control"],
            hover_color=COLORS["control_hover"], text_color=COLORS["text"],
            corner_radius=8
        )
        self.btn_copy.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        # Regen button
        self.btn_regen = ctk.CTkButton(
            self, text="⚡ Tạo lại", command=on_regen, height=36,
            font=font(11, "bold"), fg_color=COLORS["control"],
            hover_color=COLORS["control_hover"], text_color=COLORS["text"],
            corner_radius=8
        )
        self.btn_regen.grid(row=0, column=2, padx=4, pady=4, sticky="ew")

        # Next button
        self.btn_next = ctk.CTkButton(
            self, text=f"✅ {next_label}", command=on_next, height=36,
            font=font(11, "bold"), fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color="#051016",
            corner_radius=8
        )
        self.btn_next.grid(row=0, column=3, padx=4, pady=4, sticky="ew")

