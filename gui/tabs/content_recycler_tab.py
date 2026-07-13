import customtkinter as ctk

class ContentRecyclerTab(ctk.CTkFrame):
    def __init__(self, master, app_controller, **kwargs):
        super().__init__(master, **kwargs)
        self.app_controller = app_controller
        
        # UI Elements
        self.url_label = ctk.CTkLabel(self, text="Source Video URL:")
        self.url_label.pack(pady=(10, 0), padx=10, anchor="w")
        
        self.url_entry = ctk.CTkEntry(self, width=400)
        self.url_entry.pack(pady=5, padx=10, anchor="w")
        
        self.start_button = ctk.CTkButton(self, text="Start Pipeline", command=self.on_start)
        self.start_button.pack(pady=20, padx=10)
        
    def on_start(self):
        url = self.url_entry.get()
        if url and self.app_controller:
            # Placeholder for thread dispatch
            print(f"Starting pipeline for {url}")
