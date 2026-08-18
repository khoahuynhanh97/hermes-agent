import customtkinter as ctk


COLORS = {
    "app_bg": "#0b0d10",
    "surface": "#12151b",
    "surface_2": "#171b22",
    "surface_3": "#1f2630",
    "border": "#27313d",
    "border_soft": "#1d2430",
    "text": "#edf2f7",
    "muted": "#96a3b5",
    "subtle": "#64748b",
    "accent": "#38bdf8",
    "accent_hover": "#0ea5e9",
    "accent_soft": "#123344",
    "success": "#22c55e",
    "success_bg": "#12351f",
    "warning": "#f59e0b",
    "warning_bg": "#3b2a10",
    "danger": "#ef4444",
    "danger_bg": "#3a1517",
    "control": "#202631",
    "control_hover": "#2a3442",
}


def apply_theme(root):
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    root.configure(fg_color=COLORS["app_bg"])


def font(size=12, weight=None, family="Segoe UI"):
    kwargs = {"size": size, "family": family}
    if weight:
        kwargs["weight"] = weight
    return ctk.CTkFont(**kwargs)


def mono(size=11):
    return ctk.CTkFont(family="Consolas", size=size)


def primary_button_kwargs():
    return {
        "fg_color": COLORS["accent"],
        "hover_color": COLORS["accent_hover"],
        "text_color": "#051016",
        "corner_radius": 8,
        "font": font(12, "bold"),
    }


def secondary_button_kwargs():
    return {
        "fg_color": COLORS["control"],
        "hover_color": COLORS["control_hover"],
        "text_color": COLORS["text"],
        "corner_radius": 8,
        "font": font(12, "bold"),
    }
