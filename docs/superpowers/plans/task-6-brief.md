### Task 6: GUI Tab (`gui/tabs/content_recycler_tab.py`)

**Files:**
- Create: `gui/tabs/content_recycler_tab.py`
- Modify: `gui/app.py` (Add tab)
- Modify: `tests/gui/test_content_recycler_tab.py` (Mock UI Test)

**Interfaces:**
- Consumes: User inputs (Target URL, Platform)
- Produces: UI Trigger for the pipeline

- [ ] **Step 1: Write the failing test**
```python
import pytest
import customtkinter as ctk
from gui.tabs.content_recycler_tab import ContentRecyclerTab

def test_content_recycler_tab_initialization():
    root = ctk.CTk()
    tab = ContentRecyclerTab(root, None)
    
    # Assert elements exist
    assert hasattr(tab, "url_entry")
    assert hasattr(tab, "start_button")
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/gui/test_content_recycler_tab.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**
```python
# gui/tabs/content_recycler_tab.py
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
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/gui/test_content_recycler_tab.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add gui/tabs/content_recycler_tab.py tests/gui/test_content_recycler_tab.py
git commit -m "feat: implement basic content recycler GUI tab"
```
