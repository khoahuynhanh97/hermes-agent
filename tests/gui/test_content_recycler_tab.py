import pytest
import customtkinter as ctk
from gui.tabs.content_recycler_tab import ContentRecyclerTab

def test_content_recycler_tab_initialization():
    root = ctk.CTk()
    tab = ContentRecyclerTab(root, None)
    
    # Assert elements exist
    assert hasattr(tab, "url_entry")
    assert hasattr(tab, "start_button")
