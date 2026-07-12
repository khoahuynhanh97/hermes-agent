import re

# Mode string constants
MODE_LEARN_KNOWLEDGE = "learn_knowledge"
MODE_LEARN_VIDEO = "learn_video"  # legacy alias of MODE_LEARN_KNOWLEDGE
MODE_LEARN_HOOK_CTA = "learn_hook_cta"
MODE_SCRIPT_FROM_VIDEO = "script_from_video"

# Standard route mappings for commands, modes, and execution engines
ROUTE_MAP = {
    "/hoc_kien_thuc": {"mode": MODE_LEARN_KNOWLEDGE,    "engine": "knowledge"},
    "/hoc_video":     {"mode": MODE_LEARN_KNOWLEDGE,    "engine": "knowledge"},
    "/hoc_hook_cta":  {"mode": MODE_LEARN_HOOK_CTA,     "engine": "hook_cta"},
    "/len_kich_ban":  {"mode": MODE_SCRIPT_FROM_VIDEO,  "engine": "mixed"},
    "/review":        {"mode": "product_review",     "engine": "ai_studio"},
    "/htmlvideo":     {"mode": "html_video",         "engine": "html_video"},
    "/de_xuat_nang_cap": {"mode": "upgrade_audit",  "engine": "audit"},
}

def normalize_command(text: str) -> str | None:
    """
    Normalizes input text by matching Vietnamese/spaced command variations
    and returns the standard key for ROUTE_MAP lookup.
    """
    if not text:
        return None
        
    text_clean = text.strip().lower()
    
    # Matching aliases and space variations
    if text_clean.startswith(("/hoc_kien_thuc", "/hoc_kien_thuc")):
        return "/hoc_kien_thuc"
    if text_clean.startswith(("/hoc_video", "/hoc video", "/học video")):
        return "/hoc_video"
    if text_clean.startswith(("/hoc_hook_cta", "/hoc_hook_cta")):
        return "/hoc_hook_cta"
    if text_clean.startswith(("/len_kich_ban", "/len kich ban", "/lên kịch bản")):
        return "/len_kich_ban"
    if text_clean.startswith("/review"):
        return "/review"
    if text_clean.startswith("/htmlvideo"):
        return "/htmlvideo"
    if text_clean.startswith("/de_xuat_nang_cap"):
        return "/de_xuat_nang_cap"
        
    return None

def resolve_route(text: str) -> dict | None:
    """
    Analyzes input message text and returns the corresponding route configuration dictionary.
    Returns None if no matching command route is found.
    """
    cmd = normalize_command(text)
    if cmd in ROUTE_MAP:
        return ROUTE_MAP[cmd]
    return None

def get_mode(text: str) -> str | None:
    """Shortcut helper to get the mode string from message text."""
    route = resolve_route(text)
    return route["mode"] if route else None

def get_engine(text: str) -> str | None:
    """Shortcut helper to get the engine target from message text."""
    route = resolve_route(text)
    return route["engine"] if route else None
