import os
from pathlib import Path
from dotenv import load_dotenv, set_key
from hermes.config import get_data_path, get_data_root

# Load environment variables from .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Fallback to loading current directory .env if any
    load_dotenv()

# Gemini Config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Text LLM gateway. 9Router is primary; the existing provider router is the
# controlled compatibility fallback during migration.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "router")
LLM_ROUTER_BASE_URL = os.environ.get("LLM_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1")
LLM_ROUTER_API_KEY = os.environ.get("LLM_ROUTER_API_KEY", "")
LLM_DEFAULT_MODEL = os.environ.get("LLM_DEFAULT_MODEL", "reason_combo")
LLM_MODEL_CHAT = os.environ.get("LLM_MODEL_CHAT", "")
LLM_MODEL_LEARNING = os.environ.get("LLM_MODEL_LEARNING", "")
LLM_MODEL_CODE = os.environ.get("LLM_MODEL_CODE", "")
LLM_TIMEOUT_SECONDS = os.environ.get("LLM_TIMEOUT_SECONDS", "60")
LLM_RETRY_COUNT = os.environ.get("LLM_RETRY_COUNT", "1")
LLM_ENABLE_LEGACY_PROVIDER_FALLBACK = os.environ.get("LLM_ENABLE_LEGACY_PROVIDER_FALLBACK", "0")
HERMES_STORAGE_BACKEND = os.environ.get("HERMES_STORAGE_BACKEND", "sqlite")
HERMES_DATA_DIR = os.environ.get("HERMES_DATA_DIR", str(get_data_root()))
HERMES_DB_PATH = os.environ.get("HERMES_DB_PATH", str(get_data_path("db", "hermes.db")))
HERMES_BACKUP_DIR = os.environ.get("HERMES_BACKUP_DIR", "")
TELEGRAM_MAX_FILE_MB = os.environ.get("TELEGRAM_MAX_FILE_MB", "200")

# Multi-Provider AI Router Keys (9router-style)
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY   = os.environ.get("CEREBRAS_API_KEY", "")
MISTRAL_API_KEY    = os.environ.get("MISTRAL_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TOGETHER_API_KEY   = os.environ.get("TOGETHER_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
AI_ROUTER_STRATEGY = os.environ.get("AI_ROUTER_STRATEGY", "balanced")  # speed / quality / cost / balanced

# Ollama Local Model
OLLAMA_API_URL       = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
DEFAULT_LOCAL_MODEL  = os.environ.get("DEFAULT_LOCAL_MODEL", "llama3.2:3b")

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USER_IDS = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
TELEGRAM_REVIEW_CHAT_ID = os.environ.get("TELEGRAM_REVIEW_CHAT_ID", "")
TELEGRAM_REVIEW_SOURCE_CHAT = os.environ.get("TELEGRAM_REVIEW_SOURCE_CHAT", "")
HERMES_ALERTS_ENABLED = os.environ.get("HERMES_ALERTS_ENABLED", "0")

# Provider Keys
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
GROK_API_KEY = os.environ.get("GROK_API_KEY", "")
RUNWAY_API_KEY = os.environ.get("RUNWAY_API_KEY", "")
PIKA_API_KEY = os.environ.get("PIKA_API_KEY", "")
KREA_API_KEY = os.environ.get("KREA_API_KEY", "")
LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY", "")
AI_VIDEO_CUSTOM_API_KEY = os.environ.get("AI_VIDEO_CUSTOM_API_KEY", "")

# AI Video Provider Endpoints / Models
GROK_VIDEO_ENDPOINT = os.environ.get("GROK_VIDEO_ENDPOINT", "")
RUNWAY_VIDEO_ENDPOINT = os.environ.get("RUNWAY_VIDEO_ENDPOINT", "")
PIKA_VIDEO_ENDPOINT = os.environ.get("PIKA_VIDEO_ENDPOINT", "")
KREA_VIDEO_ENDPOINT = os.environ.get("KREA_VIDEO_ENDPOINT", "")
LEONARDO_VIDEO_ENDPOINT = os.environ.get("LEONARDO_VIDEO_ENDPOINT", "")
AI_VIDEO_CUSTOM_ENDPOINT = os.environ.get("AI_VIDEO_CUSTOM_ENDPOINT", "")
GROK_VIDEO_MODEL = os.environ.get("GROK_VIDEO_MODEL", "grok-imagine")
RUNWAY_VIDEO_MODEL = os.environ.get("RUNWAY_VIDEO_MODEL", "gen4_turbo")
PIKA_VIDEO_MODEL = os.environ.get("PIKA_VIDEO_MODEL", "pika-2.5")
KREA_VIDEO_MODEL = os.environ.get("KREA_VIDEO_MODEL", "auto")
LEONARDO_VIDEO_MODEL = os.environ.get("LEONARDO_VIDEO_MODEL", "motion-2.0-fast")
AI_VIDEO_CUSTOM_MODEL = os.environ.get("AI_VIDEO_CUSTOM_MODEL", "video-model")
AI_VIDEO_POLL_SECONDS = os.environ.get("AI_VIDEO_POLL_SECONDS", "5")
AI_VIDEO_MAX_WAIT_SECONDS = os.environ.get("AI_VIDEO_MAX_WAIT_SECONDS", "600")

# YouTube Publishing
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REDIRECT_URI = os.environ.get("YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/publish/youtube/callback")
YOUTUBE_ACCESS_TOKEN = os.environ.get("YOUTUBE_ACCESS_TOKEN", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

# Instagram Publishing
INSTAGRAM_CLIENT_ID = os.environ.get("INSTAGRAM_CLIENT_ID", "")
INSTAGRAM_CLIENT_SECRET = os.environ.get("INSTAGRAM_CLIENT_SECRET", "")
INSTAGRAM_REDIRECT_URI = os.environ.get("INSTAGRAM_REDIRECT_URI", "http://localhost:8000/api/publish/instagram/callback")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_BUSINESS_ACCOUNT_ID = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

# Paths
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "")
PROJECTS_ROOT = os.environ.get("PROJECTS_ROOT", "projects")
KNOWLEDGE_BASE_ROOT = os.environ.get("KNOWLEDGE_BASE_ROOT", "knowledge_base")

def save_config(gemini_key, gemini_model, pexels_key, pixabay_key, ffmpeg_path, projects_root="projects", ai_video_keys=None):
    """Saves the configuration parameters back to the .env file and updates current state."""
    global GEMINI_API_KEY, GEMINI_MODEL, PEXELS_API_KEY, PIXABAY_API_KEY, FFMPEG_PATH, PROJECTS_ROOT
    global GROK_API_KEY, RUNWAY_API_KEY, PIKA_API_KEY, KREA_API_KEY, LEONARDO_API_KEY, AI_VIDEO_CUSTOM_API_KEY
    global AI_VIDEO_CUSTOM_ENDPOINT
    
    # Ensure file exists
    if not os.path.exists(env_path):
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write("# Hermes TikTok Video Factory - Configuration\n")
            
    # Save using set_key from python-dotenv to preserve comments/order
    set_key(env_path, "GEMINI_API_KEY", gemini_key)
    set_key(env_path, "GEMINI_MODEL", gemini_model)
    set_key(env_path, "PEXELS_API_KEY", pexels_key)
    set_key(env_path, "PIXABAY_API_KEY", pixabay_key)
    set_key(env_path, "FFMPEG_PATH", ffmpeg_path)
    set_key(env_path, "PROJECTS_ROOT", projects_root)

    if ai_video_keys:
        for key, value in ai_video_keys.items():
            set_key(env_path, key, value)
    
    # Reload values in memory
    GEMINI_API_KEY = gemini_key
    GEMINI_MODEL = gemini_model
    PEXELS_API_KEY = pexels_key
    PIXABAY_API_KEY = pixabay_key
    FFMPEG_PATH = ffmpeg_path
    PROJECTS_ROOT = projects_root
    if ai_video_keys:
        GROK_API_KEY = ai_video_keys.get("GROK_API_KEY", GROK_API_KEY)
        RUNWAY_API_KEY = ai_video_keys.get("RUNWAY_API_KEY", RUNWAY_API_KEY)
        PIKA_API_KEY = ai_video_keys.get("PIKA_API_KEY", PIKA_API_KEY)
        KREA_API_KEY = ai_video_keys.get("KREA_API_KEY", KREA_API_KEY)
        AI_VIDEO_CUSTOM_ENDPOINT = ai_video_keys.get("AI_VIDEO_CUSTOM_ENDPOINT", AI_VIDEO_CUSTOM_ENDPOINT)

def verify_config():
    """Kiểm tra các trường cấu hình quan trọng và cảnh báo nếu thiếu."""
    missing = []
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        missing.append("GEMINI_API_KEY (Bắt buộc cho AI Script, Video Analyser và các tính năng AI khác)")
    if not TELEGRAM_BOT_TOKEN:
        # Bot token is optional but critical if they are running the Telegram bot
        missing.append("TELEGRAM_BOT_TOKEN (Không bắt buộc, chỉ cần nếu bạn muốn chạy Bot Telegram)")
        
    if missing:
        print("\n" + "="*60)
        print("[!] CẢNH BÁO: CẤU HÌNH HỆ THỐNG CHƯA HOÀN THIỆN")
        for item in missing:
            print(f"  - {item}")
        print("-> Vui lòng mở tệp '.env' và cập nhật đầy đủ các trường cấu hình trên.")
        print("="*60 + "\n")
        return False
    return True
