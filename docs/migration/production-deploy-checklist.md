# Production Deployment Checklist

Use this checklist before each production release.

## 1. Git and Release Readiness
- [ ] All migration changes are pushed to the remote branch.
- [ ] CI is green for backend tests and frontend build.
- [ ] A rollback reference exists (tag or backup branch).

## 2. Backend Environment
- [ ] `COSAI_ENV=production` (or `ENV=production`) is set.
- [ ] `COSAI_SESSION_SECRET` is set and is not the development fallback secret.
- [ ] `DATABASE_URL` points to the production Postgres instance.
- [ ] `COSAI_API_CORS_ORIGINS` includes production frontend origin.

## 3. OAuth Configuration
- [ ] `COSAI_REDIRECT_URI` includes the production frontend URL.
- [ ] Google OAuth Authorized redirect URIs include the same production frontend URL.
- [ ] Local and staging callback URLs remain present if you still need them.

## 4. Frontend Environment
- [ ] `VITE_API_BASE_URL` points to the production API URL.
- [ ] Frontend domain is HTTPS.

## 5. Security and Session
- [ ] Session endpoint checks pass (`/v1/auth/me`, `/v1/auth/refresh`).
- [ ] Token refresh works from frontend on reload.
- [ ] No development secrets are used in production.

## 6. Functional Smoke Checks
- [ ] Google sign-in succeeds from production frontend.
- [ ] Task list loads from `/v1/me/tasks`.
- [ ] Task create and mark-done flows work.
- [ ] Accounts list and query filter update work.
- [ ] Insights summary loads.

## 7. Observability
- [ ] Error monitoring is enabled.
- [ ] API logs are accessible.
- [ ] Alerting is configured for API 5xx spikes.

## 8. Rollback Plan
- [ ] Previous stable deployment target is known.
- [ ] Database backup was taken before release.
- [ ] Rollback steps are documented and tested.

## Mandatory Reminder
After pushing release changes, add or verify the production frontend callback URL in both places:
- Google OAuth Authorized redirect URIs
- Production `COSAI_REDIRECT_URI`