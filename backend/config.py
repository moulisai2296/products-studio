"""Central config + feature flags for PhotoDukaan.

Everything that reads an env var lives here so the rest of the code never calls
os.getenv directly. Flip MOCK_MODE / DEMO_FALLBACK / LANGFUSE_ENABLED here.
"""
import os


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


# --- Core modes -----------------------------------------------------------
MOCK_MODE = _flag("MOCK_MODE", "1")          # 1 = zero external deps (safe default)
DEMO_FALLBACK = _flag("DEMO_FALLBACK", "0")  # 1 = always serve seed/ assets (network-death insurance)

# --- Keys / endpoints -----------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

DRIVE_PARENT_FOLDER_ID = os.getenv("DRIVE_PARENT_FOLDER_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

LANGFUSE_ENABLED = _flag("LANGFUSE_ENABLED", "0")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Public base URL this backend is reachable at (used to build asset URLs).
# On Render set PUBLIC_BASE_URL=https://<service>.onrender.com
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

# --- Timeouts (seconds) — CLAUDE.md §1.4 ----------------------------------
TIMEOUT_IMAGE = float(os.getenv("TIMEOUT_IMAGE", "30"))
TIMEOUT_VIDEO = float(os.getenv("TIMEOUT_VIDEO", "120"))
TIMEOUT_DRIVE = float(os.getenv("TIMEOUT_DRIVE", "10"))
TIMEOUT_SUPABASE = float(os.getenv("TIMEOUT_SUPABASE", "10"))
TIMEOUT_DIRECTOR = float(os.getenv("TIMEOUT_DIRECTOR", "30"))

# --- Model strings (verified — CLAUDE.md §3) ------------------------------
MODEL_DIRECTOR = "gemini-3.5-flash"
MODEL_ANGLE = "gemini-3.1-flash-lite-image"   # NB2 Lite
MODEL_EDIT = "gemini-3.1-flash-image"         # NB2
MODEL_REEL = "gemini-omni-flash-preview"      # Omni Flash

# --- Hardcoded cost table (CLAUDE.md §7) ----------------------------------
COST_ANGLE = 0.034
COST_EDIT = 0.067
COST_REEL_PER_SEC = 0.10  # ~$1.00 per 10s reel
REEL_SECONDS = 10

# --- Static asset dir -----------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
SEED_URL = f"{PUBLIC_BASE_URL}/static/seed"
