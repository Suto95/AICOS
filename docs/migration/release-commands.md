# Release Commands

## 1) Verify local branch and tests

```bash
git status --short
PYTHONPATH=. .venv/bin/python -m unittest -q archive.tests.aicos_api.test_api_migration
cd web && npm run build && cd ..
```

## 2) Commit and push

```bash
git add .
git commit -m "React migration: API + auth + release hardening"
git push origin <your-branch>
```

## 3) Pre-deploy verification (production mode)

```bash
./tools/migration/predeploy_verify.sh --mode production --frontend-url https://your-frontend-domain.com/ --env-file .env.production
```

## 4) Deploy API and frontend to staging

Use your platform workflows (Render/Railway/Fly for API, Vercel/Netlify/Pages for frontend).

## 5) Staging smoke checks

```bash
# API health
curl -s https://your-api-domain.com/health

# Verify predeploy script can run against staged env file values
./tools/migration/predeploy_verify.sh --mode production --frontend-url https://your-frontend-domain.com/ --env-file .env.production
```

## 6) Production cutover

- Promote staging builds to production.
- Monitor logs and errors for at least 30 minutes.
- Keep rollback deployment target ready.

## Mandatory OAuth reminder

After pushing release changes, ensure your production frontend URL is present in both:
- Google OAuth Authorized redirect URIs
- Production COSAI_REDIRECT_URI
