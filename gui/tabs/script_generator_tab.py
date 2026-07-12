import os
import sys
import customtkinter as ctk

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from gui.theme import COLORS, secondary_button_kwargs
from gui.components import LabeledTextbox
from core.script_generator import SCRIPT_STYLES
import core.knowledge_base as kb

class ScriptGeneratorTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance

        self.tab.grid_columnconfigure(0, weight=1)
        
        row_style = ctk.CTkFrame(self.tab, fg_color="transparent")
        row_style.pack(fill="x", padx=20, pady=(15, 8))
        
        lbl_style = ctk.CTkLabel(row_style, text="Chọn phong cách kịch bản:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_style.pack(side="left")
        
        self.app.script_style_combo = ctk.CTkComboBox(row_style, values=list(SCRIPT_STYLES.keys()), width=250, state="readonly")
        self.app.script_style_combo.pack(side="left", padx=15)
        self.app.script_style_combo.set("Mở đầu tò mò")
        
        self.app.btn_gen_script = ctk.CTkButton(row_style, text="Viết kịch bản mới (AI Gemini)", command=self.app.generate_project_script, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.app.btn_gen_script.pack(side="left", padx=10)
        
        # Row for learned template selection
        row_learned = ctk.CTkFrame(self.tab, fg_color="transparent")
        row_learned.pack(fill="x", padx=20, pady=(0, 10))
        
        lbl_learned = ctk.CTkLabel(row_learned, text="Học theo phong cách video:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_learned.pack(side="left")
        
        self.app.script_learned_combo = ctk.CTkComboBox(row_learned, values=["Không áp dụng"], width=420, state="readonly")
        self.app.script_learned_combo.pack(side="left", padx=15)
        self.app.script_learned_combo.set("Không áp dụng")
        
        btn_refresh_learned = ctk.CTkButton(
            row_learned, text="🔄 Làm mới", width=80, **secondary_button_kwargs(),
            command=self.script_refresh_learned_dropdown
        )
        btn_refresh_learned.pack(side="left")
        
        # Script box Labeled
        self.app.script_display_box = LabeledTextbox(self.tab, "Lời thoại Thuyết minh (Dùng nạp giọng đọc ElevenLabs):", height=240)
        self.app.script_display_box.pack(fill="both", expand=True, padx=20, pady=5)
        
        row_footer = ctk.CTkFrame(self.tab, fg_color="transparent")
        row_footer.pack(fill="x", padx=20, pady=15)
        
        self.app.btn_copy_script = ctk.CTkButton(row_footer, text="Sao chép kịch bản vào Clipboard", command=self.app.copy_script_to_clipboard, height=35)
        self.app.btn_copy_script.pack(side="left")

        # Initialize and populate learned dropdown choices
        self.app.kb_slug_mapping = {}
        self.script_refresh_learned_dropdown()

    def script_refresh_learned_dropdown(self):
        """Tải danh sách các video đã học và hiển thị vào combobox kịch bản."""
        learned_list = kb.load_learned_list()
        self.app.kb_slug_mapping = {}
        choices = ["Không áp dụng"]
        
        for item in learned_list:
            display_name = f"[{item.get('platform', 'N/A')}] {item.get('title', 'Bài học')}"
            choices.append(display_name)
            self.app.kb_slug_mapping[display_name] = item.get("slug")
            
        self.app.script_learned_combo.configure(values=choices)
        
        # Reset if current selection is invalid
        current = self.app.script_learned_combo.get()
        if current not in choices:
            self.app.script_learned_combo.set("Không áp dụng")
