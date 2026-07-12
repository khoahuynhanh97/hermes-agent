import os
import sys
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.assistant_runtime import HermesAssistantRuntime
from core.coding_agent import CodingAgentPlanner
from core.tool_registry import ToolRegistry
from gui.components import LabeledTextbox
from gui.theme import COLORS, secondary_button_kwargs


class AssistantTab:
    def __init__(self, parent_tab, app_instance):
        self.tab = parent_tab
        self.app = app_instance
        self.repo_root = Path(__file__).resolve().parents[2]
        self.runtime = HermesAssistantRuntime(self.repo_root)
        self.code_planner = CodingAgentPlanner(self.repo_root)
        self.tool_registry = ToolRegistry(self.repo_root)

        self.tab.grid_columnconfigure(0, weight=3)
        self.tab.grid_columnconfigure(1, weight=7)
        self.tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self.tab, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(self.tab, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            left,
            text="Hermes Assistant",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#60a5fa",
        ).grid(row=0, column=0, sticky="w", pady=(5, 2))
        ctk.CTkLabel(
            left,
            text="Plan requests, code changes, and local tools. Dry-run by default.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        self.request_box = LabeledTextbox(left, "Request", height=150)
        self.request_box.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkButton(
            left,
            text="Assistant Plan",
            command=self.run_assistant_plan,
            height=34,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
        ).grid(row=3, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkButton(
            left,
            text="Code Plan",
            command=self.run_code_plan,
            height=34,
            fg_color="#10b981",
            hover_color="#059669",
        ).grid(row=4, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkButton(
            left,
            text="Refresh Tools",
            command=self.refresh_tools,
            height=32,
            **secondary_button_kwargs(),
        ).grid(row=5, column=0, sticky="ew", pady=(0, 12))

        self.tools_box = LabeledTextbox(left, "Registered tools", height=180)
        self.tools_box.grid(row=6, column=0, sticky="nsew")
        left.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(
            right,
            text="Plan Output",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w", pady=(5, 6))
        self.output_box = ctk.CTkTextbox(
            right,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            fg_color="#0d1117",
            text_color="#d7e0ef",
        )
        self.output_box.grid(row=1, column=0, sticky="nsew")
        self.refresh_tools()

    def run_assistant_plan(self):
        request = self.request_box.get().strip()
        if not request:
            messagebox.showinfo("Hermes Assistant", "Enter a request first.")
            return
        plan = self.runtime.build_plan(request)
        self.set_output(self.runtime.format_markdown(plan))

    def run_code_plan(self):
        request = self.request_box.get().strip()
        if not request:
            messagebox.showinfo("Hermes Assistant", "Enter a coding request first.")
            return
        plan = self.code_planner.build_plan(request)
        report_path = self.code_planner.write_report(plan)
        output = self.code_planner.format_markdown(plan)
        output += f"\nReport written: {report_path}\n"
        self.set_output(output)

    def refresh_tools(self):
        rows = []
        for manifest in self.tool_registry.list_manifests():
            status = "valid" if manifest.valid else "invalid"
            rows.append(f"{manifest.name} | {status} | {manifest.data.get('description', '')}")
            for error in manifest.errors:
                rows.append(f"  - {error}")
        self.tools_box.set("\n".join(rows) if rows else "No registered tools.")

    def set_output(self, text):
        self.output_box.delete("1.0", "end")
        self.output_box.insert("1.0", text)
