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
# How long Ollama keeps the model in memory after the last request ("15m", "1h", "-1" = forever).
# Ollama's own default is 5 minutes; loading the model again takes time.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")

# --- RAG: add the closest solved examples (ibn/vendors/<vendor>/examples.json) to the AI's prompt ---
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
RAG_SOURCES = [s.strip() for s in os.getenv("RAG_SOURCES", "examples,docs").split(",") if s.strip()]
RAG_SEARCH = os.getenv("RAG_SEARCH", "embedding")      # "embedding" (needs RAG_EMBED_MODEL) or "keyword"
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "bge-m3")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))             # how many chunks per source go into the prompt

# --- Knowledge base: devices, links and history, saved in one JSON file ---
KB_FILE = os.getenv("KB_FILE", "data/knowledge.json")

# --- Infrastructure ---
# Default login used for devices (one shared account keeps things simple).
DEVICE_USERNAME = os.getenv("DEVICE_USERNAME", "admin")
DEVICE_PASSWORD = os.getenv("DEVICE_PASSWORD", "admin")
DEVICE_SECRET = os.getenv("DEVICE_SECRET", "")  # Cisco "enable" password

# true = do everything except really sending config to devices
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
