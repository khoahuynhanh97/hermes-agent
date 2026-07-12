import os
from dotenv import load_dotenv, set_key

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
