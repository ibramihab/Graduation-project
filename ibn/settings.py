"""All settings in one place. Values come from the .env file (see .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- Intent layer (the AI) ---
# "claude" = cloud LLM with an API key (ANTHROPIC_API_KEY)
# "ollama" = local LLM running on your own machine (future / offline)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# --- Knowledge base ---
# "neo4j" = real graph database (run it with docker compose)
# "file"  = tiny graph saved in a JSON file (no install needed, good for learning)
KB_BACKEND = os.getenv("KB_BACKEND", "file")
KB_FILE = os.getenv("KB_FILE", "data/knowledge.json")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# --- Infrastructure ---
# Default login used for devices (one shared account keeps things simple).
DEVICE_USERNAME = os.getenv("DEVICE_USERNAME", "admin")
DEVICE_PASSWORD = os.getenv("DEVICE_PASSWORD", "admin")
DEVICE_SECRET = os.getenv("DEVICE_SECRET", "")  # Cisco "enable" password

# true = show the browser window when the AI controls a web-page router (web_gui)
SHOW_BROWSER = os.getenv("SHOW_BROWSER", "true").lower() == "true"
# optional: path to a Chrome/Chromium to use instead of Playwright's own browser
BROWSER_PATH = os.getenv("BROWSER_PATH", "")

# true = do everything except really sending config to devices
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
