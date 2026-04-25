"""AICOS app package."""

from pathlib import Path

from dotenv import load_dotenv

# Ensure every Streamlit page loads the same env vars, even if config.py is not imported.
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)

# Initialize Sentry for error tracking (only if DSN is provided)
try:
    import sentry_sdk
    from sentry_sdk.integrations.streamlit import StreamlitIntegration

    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[StreamlitIntegration()],
            traces_sample_rate=1.0,
            environment="production" if os.getenv("STREAMLIT_SERVER_HEADLESS") else "development"
        )
except ImportError:
    pass  # Sentry not installed, skip
