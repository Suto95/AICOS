import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PREF_FILE = "user_prefs.json"
MEMORY_FILE = "task_memory.jsonl"
EVENT_FILE = "task_events.jsonl"

SIGNAL_FIELDS = (
    "deadline",
    "penalty_for_delay",
    "blocks_others",
    "outcome_value",
    "strategic_alignment",
    "reversibility",
    "visibility",
)
LEARNABLE_FIELDS = ("outcome_value", "strategic_alignment", "blocks_others")

IMPACT_WEIGHTS = {
    "deadline": 0.9,
    "penalty_for_delay": 0.8,
    "blocks_others": 0.85,
    "outcome_value": 0.9,
    "strategic_alignment": 0.85,
    "visibility": 0.7,
    "reversibility": 0.6,
}

IMPORTANCE_MAP = {"low": 0.3, "medium": 0.6, "high": 1.0}
FIELD_CHOICES = {
    "penalty_for_delay": ("yes", "no"),
    "blocks_others": ("yes", "no"),
    "outcome_value": ("low", "medium", "high"),
    "strategic_alignment": ("low", "medium", "high"),
    "reversibility": ("low", "medium", "high"),
    "visibility": ("low", "medium", "high"),
}
INFER_THRESHOLDS = {
    "deadline": 0.85,
    "penalty_for_delay": 0.78,
    "blocks_others": 0.78,
    "outcome_value": 0.72,
    "strategic_alignment": 0.72,
    "reversibility": 0.7,
    "visibility": 0.7,
}
BUCKET_ORDER = ("DO NOW", "SCHEDULE", "DELEGATE", "REVIEW LATER", "ELIMINATE", "ERROR")

client = OpenAI(api_key=os.getenv("OAI_API_KEY"))
