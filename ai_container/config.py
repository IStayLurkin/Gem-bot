import os
from dotenv import load_dotenv

load_dotenv()

# --- DISCORD CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
target_channels_env = os.getenv("TARGET_CHANNEL_ID", "")
TARGET_CHANNEL_IDS = [id.strip() for id in target_channels_env.split(',') if id.strip()]

# --- API KEYS ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")

# --- LLM MODELS ---
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "llama3")
TTS_MODEL = "gemini-2.5-flash-preview-tts"
VISION_MODEL = "gemini-5-flash-preview-09-2025"

# --- GEMINI API BASE ---
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"

# --- SQLITE CONFIGURATION ---
DB_PATH = os.path.join(os.path.dirname(__file__), "gem_memory.db")

# --- LOCAL IMAGE GENERATION CONFIG ---
LOCAL_SD_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "sdxl")
LOCAL_SD_ENABLED = os.getenv("LOCAL_SD_ENABLED", "false").lower() == "true"
LOCAL_SD_DEVICE = os.getenv("LOCAL_SD_DEVICE", "cuda")  # cuda or cpu
LOCAL_SD_STEPS = int(os.getenv("LOCAL_SD_STEPS", "30"))
LOCAL_SD_GUIDANCE = float(os.getenv("LOCAL_SD_GUIDANCE", "6.0"))

# --- GENERAL GLOBALS ---
APP_ID = "default-app-id"
MASTER_USER_ID = "PRIMARY_USER"

# --- RUNTIME GLOBALS (Initialized as None) ---
OLLAMA_URL = None
SD_URL = None
SVD_URL = None

# --- JOB QUEUES ---
VIDEO_JOBS = {}
IMAGE_JOBS = {}

# --- DYNAMIC CONFIG (Fallback/Default) ---
GLOBAL_CONFIG = {
    'MAX_HISTORY_LENGTH': 10,
    'FORGET_CHANCE': 5,
    'POLLING_INTERVAL': 30,
    'MAX_TOOL_RESULT_LENGTH': 2000,
}

