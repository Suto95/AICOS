# AICOS - Production Deployment Guide

## Organized Project Layout
All required AICOS files are now grouped under the `aicos/` folder:

- `aicos/cosai_app/` - Streamlit app package
- `aicos/.streamlit/` - Streamlit secrets/config
- `aicos/migrate_to_postgres.py` - DB migration utility
- `aicos/cosai_app.db` - local SQLite DB
- `aicos/task_memory.jsonl`, `aicos/task_events.jsonl`, `aicos/user_prefs.json` - local app data

Compatibility symlinks are kept at the repository root, so old commands continue to work.

Run commands:

```bash
streamlit run aicos/cosai_app/streamlit_app.py
python3 aicos/migrate_to_postgres.py
```

## Overview
AICOS is a Streamlit-based AI task prioritization app that integrates with Gmail. This guide covers making it production-ready for multiple users.

## Prerequisites
- Google Cloud Console project with OAuth 2.0 credentials
- PostgreSQL database (e.g., from Supabase, Heroku Postgres, or AWS RDS)
- GitHub repository
- Streamlit Cloud account

## 1. Database Migration

### Migrate from SQLite to PostgreSQL

1. **Install PostgreSQL dependencies:**
   ```bash
   pip install psycopg2-binary
   ```
   This package is required for production PostgreSQL support when deploying to Streamlit Cloud.

2. **Set environment variables:**
   ```bash
   export SQLITE_DB_PATH="cosai_app.db"
   export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
   ```

3. **Run migration:**
   ```bash
   python migrate_to_postgres.py
   ```

4. **Update `cosai_app/db.py`** to use PostgreSQL instead of SQLite.

## 2. Environment Configuration

### Create `.streamlit/secrets.toml`:
```toml
GOOGLE_OAUTH_CLIENT_ID = "your-client-id"
GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"
COSAI_REDIRECT_URI = "https://your-app.streamlit.app/"
DATABASE_URL = "postgresql://..."
COSAI_ENCRYPTION_KEY = "32-char-key"
GOOGLE_ANALYTICS_ID = "GA4-ID"
SENTRY_DSN = "your-sentry-dsn"
```

### For Streamlit Cloud:
- Go to your app → Settings → Secrets
- Add all secrets from `secrets.toml`

## 3. CI/CD with GitHub Actions

The `.github/workflows/deploy.yml` handles:
- Automated testing on PRs
- Deployment to Streamlit Cloud on main branch pushes

## 4. Error Logging & Analytics

### Sentry (Error Tracking)
- Sign up at [sentry.io](https://sentry.io)
- Create a new project for Streamlit
- Add DSN to secrets
- Errors are automatically captured

### Google Analytics (Usage Tracking)
- Create GA4 property
- Add measurement ID to secrets
- Tracks page views, user interactions

## 5. Deployment Steps

1. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Production ready"
   git push origin main
   ```

2. **Deploy to Streamlit Cloud:**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Connect your GitHub repo
   - Set main file path: `cosai_app/streamlit_app.py`
   - Deploy

3. **Configure OAuth Redirect URI:**
   - In Google Cloud Console → APIs & Credentials
   - Add authorized redirect URI: `https://your-app.streamlit.app/`

## 6. Monitoring & Maintenance

### View Analytics:
- Google Analytics dashboard for user behavior
- Sentry dashboard for error rates and issues

### Scaling Considerations:
- For >100 users, consider Redis for session storage
- Monitor PostgreSQL performance
- Set up database backups

## Troubleshooting

### Common Issues:
- **OAuth errors:** Check redirect URI matches exactly
- **Database connection:** Verify DATABASE_URL format
- **Secrets not loading:** Ensure they're set in Streamlit Cloud settings

### Logs:
- Check Streamlit Cloud logs in the app dashboard
- Sentry for detailed error traces
