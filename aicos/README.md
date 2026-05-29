# AICOS - Production Deployment Guide

## Project Layout
The active AICOS source lives under `aicos/`.

- `aicos/cosai_app/` - Streamlit app package
- `aicos/.streamlit/` - Streamlit configuration and secrets
- `aicos/migrate_to_postgres.py` - SQLite to PostgreSQL migration utility
- `aicos/cosai_app.db` - local SQLite database used in development
- `aicos/task_memory.jsonl`, `aicos/task_events.jsonl`, `aicos/user_prefs.json` - local app state files

Root-level copies of the database and JSONL files also exist for legacy compatibility. The recommended entrypoint is `aicos/cosai_app/streamlit_app.py`.

## Overview
AICOS is a Streamlit-based AI task prioritization app with Gmail integration. This README explains local development, database migration, and production deployment.

## Prerequisites
- Python 3.11+ and a virtual environment
- Google Cloud Console project with OAuth 2.0 credentials
- PostgreSQL database for production (Supabase, Heroku, AWS RDS, etc.)
- GitHub repository for source control
- Streamlit Cloud account for deployment

## 0. Setup
Install dependencies and activate your virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 1. Running Locally
Launch the Streamlit app from the `aicos/` package.

```bash
streamlit run aicos/cosai_app/streamlit_app.py
```

If you need to run the root copy of the app, use the same command because the source is centralized under `aicos/cosai_app/`.

## 2. Database Migration

### Migrate from SQLite to PostgreSQL

1. Install the PostgreSQL adapter if it is not already installed:

```bash
python -m pip install psycopg2-binary
```

2. Set environment variables for local migration.

```bash
export SQLITE_DB_PATH="cosai_app.db"
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
```

3. Run the migration script from the `aicos/` folder:

```bash
python aicos/migrate_to_postgres.py
```

4. Confirm the `aicos/cosai_app/db.py` configuration is pointed at PostgreSQL when deploying to production.

## 3. Environment Configuration

### Local environment with `.env`
For local development, the project supports `.env` via `python-dotenv`.

Example `.env` values:

```env
GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
COSAI_REDIRECT_URI=http://localhost:8501/
DATABASE_URL=postgresql://user:pass@host:5432/dbname
COSAI_ENCRYPTION_KEY=your-32-char-key
GOOGLE_ANALYTICS_ID=G-XXXXXXXXXX
SENTRY_DSN=https://example@sentry.io/123
```

### Streamlit Cloud secrets
For deployment, add the same secrets to Streamlit Cloud under app settings.

```toml
GOOGLE_OAUTH_CLIENT_ID = "your-client-id"
GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"
COSAI_REDIRECT_URI = "https://your-app.streamlit.app/"
DATABASE_URL = "postgresql://..."
COSAI_ENCRYPTION_KEY = "your-32-char-key"
GOOGLE_ANALYTICS_ID = "G-XXXXXXXXXX"
SENTRY_DSN = "https://example@sentry.io/123"
```

## 4. Deployment

### GitHub
Push your changes to the main branch.

```bash
git add .
git commit -m "Production ready"
git push origin main
```

### Streamlit Cloud
- Open [share.streamlit.io](https://share.streamlit.io)
- Connect your GitHub repository
- Set the main file path to `aicos/cosai_app/streamlit_app.py`
- Add secrets in the app settings
- Deploy

### OAuth redirect URI
In Google Cloud Console, add an authorized redirect URI matching your deployed app.

- Local development: `http://localhost:8501/`
- Streamlit deployment: `https://your-app.streamlit.app/`

## 5. Logging and Monitoring

### Sentry
- Sign up at https://sentry.io
- Create a Streamlit project
- Add `SENTRY_DSN` to your secrets

### Analytics
- Create a GA4 property
- Add the measurement ID to `GOOGLE_ANALYTICS_ID`

## 6. Troubleshooting

- **OAuth errors:** Verify redirect URI matches exactly
- **PostgreSQL connection failures:** Confirm `DATABASE_URL` format and credentials
- **Secrets not loading:** Ensure Streamlit Cloud secrets are configured or `.env` is present locally
- **Streamlit errors:** Review logs in the Streamlit dashboard

## Notes
- The active application package is `aicos/cosai_app/`
- The root `aicos/` folder contains the current source tree and migration scripts
- Root-level copies of data files exist for backward compatibility with older scripts
