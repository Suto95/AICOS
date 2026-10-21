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

SUPPORTED_LLM_PROVIDERS = ("openai", "openrouter")
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_OPENAI_PRIMARY_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_FALLBACK_MODEL = "gpt-4o-mini"
DEFAULT_OPENROUTER_PRIMARY_MODEL = "openrouter/free"
DEFAULT_OPENROUTER_FALLBACK_MODEL = "openrouter/free"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_openai_api_key():
    # Support both legacy and standard variable names.
    key = (os.getenv("OAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    return key or None


def get_openrouter_api_key():
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return key or None


def get_openrouter_base_url():
    return os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip() or DEFAULT_OPENROUTER_BASE_URL


def normalize_llm_provider(provider):
    normalized = (provider or DEFAULT_LLM_PROVIDER).strip().lower()
    if normalized not in SUPPORTED_LLM_PROVIDERS:
        return DEFAULT_LLM_PROVIDER
    return normalized


def get_default_models(provider):
    provider = normalize_llm_provider(provider)
    if provider == "openrouter":
        return {
            "primary_model": DEFAULT_OPENROUTER_PRIMARY_MODEL,
            "fallback_model": DEFAULT_OPENROUTER_FALLBACK_MODEL,
        }
    return {
        "primary_model": DEFAULT_OPENAI_PRIMARY_MODEL,
        "fallback_model": DEFAULT_OPENAI_FALLBACK_MODEL,
    }


def ensure_openai_configured():
    if not get_openai_api_key():
        raise RuntimeError(
            "OpenAI API key is missing. Set OAI_API_KEY (or OPENAI_API_KEY) in .env and restart Streamlit."
        )


def ensure_provider_configured(provider, api_key=None):
    provider = normalize_llm_provider(provider)

    if provider == "openrouter":
        key = (api_key or get_openrouter_api_key() or "").strip()
        if not key:
            raise RuntimeError(
                "OpenRouter API key is missing. Add it in AI Provider Settings or set OPENROUTER_API_KEY in .env."
            )
        return

    key = (api_key or get_openai_api_key() or "").strip()
    if not key:
        raise RuntimeError(
            "OpenAI API key is missing. Add it in AI Provider Settings or set OAI_API_KEY / OPENAI_API_KEY in .env."
        )


def get_openai_client():
    ensure_openai_configured()
    return OpenAI(api_key=get_openai_api_key())


def get_openrouter_client(api_key=None, base_url=None, allow_env_fallback=True):
    if allow_env_fallback:
        ensure_provider_configured("openrouter", api_key=api_key)
        key = (api_key or get_openrouter_api_key()).strip()
    else:
        ensure_provider_configured("openrouter", api_key=api_key)
        key = (api_key or "").strip()
    return OpenAI(api_key=key, base_url=(base_url or get_openrouter_base_url()).strip())


def get_llm_client(provider=DEFAULT_LLM_PROVIDER, api_key=None, base_url=None, allow_env_fallback=True):
    provider = normalize_llm_provider(provider)
    if provider == "openrouter":
        return get_openrouter_client(api_key=api_key, base_url=base_url, allow_env_fallback=allow_env_fallback)

    if api_key:
        ensure_provider_configured("openai", api_key=api_key)
        return OpenAI(api_key=api_key.strip())

    if not allow_env_fallback:
        ensure_provider_configured("openai", api_key=api_key)
        return OpenAI(api_key=(api_key or "").strip())

    return get_openai_client()


def create_chat_completion(
    provider,
    model,
    messages,
    temperature=0,
    max_tokens=None,
    api_key=None,
    base_url=None,
    allow_env_fallback=True,
):
    provider = normalize_llm_provider(provider)
    client = get_llm_client(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        allow_env_fallback=allow_env_fallback,
    )
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    return client.chat.completions.create(**payload)