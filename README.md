# AI Career Copilot

Production-minded career automation platform for students: resume parsing, candidate intelligence, semantic job matching, multi-platform job discovery, ATS resume tailoring, notifications, and usage limits.

## Stack
Next.js + FastAPI + SQLAlchemy/PostgreSQL + n8n + Groq + local embeddings.

## Services

| Port | Service |
| --- | --- |
| 3000 | Next.js frontend |
| 8001 | FastAPI backend |
| 8002 | Job search service |

## Quick Start

```powershell
npm run dev
```

This starts the frontend and backend together. If the backend venv was moved or copied, recreate it:

```powershell
Remove-Item -Recurse -Force .\backend\.venv
py -3.9 -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
npm run dev
```

## Backend Environment

Create `backend/.env` from `backend/.env.example` and set production values before deployment.

Important variables:

```env
ENVIRONMENT=production
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME
JWT_SECRET=replace-with-a-long-random-production-secret
BASE_API_URL=https://api.yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
RESUME_TAILORING_WEBHOOK_URL=https://n8n.yourdomain.com/webhook/tailor-resume
RESUME_INTELLIGENCE_WEBHOOK_URL=https://n8n.yourdomain.com/webhook/resume-intelligence
EMAIL_PROVIDER=smtp # use file locally to write emails into backend/email_outbox
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_USERNAME=no-reply@yourdomain.com
SMTP_PASSWORD=replace-me
SMTP_FROM=no-reply@yourdomain.com
SMTP_TLS=true
```

## Local Email Testing

Set `EMAIL_PROVIDER=file` locally; forgot-password, verify-email, and resume-ready emails are written to `backend/email_outbox`. Use SMTP credentials in production.

## Core APIs

- Auth: `POST /signup`, `POST /login`, `POST /refresh`
- Password/email: `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/verify-email`
- Profile: `GET /api/profile/me`, `POST /api/profile/create`, `PUT /api/profile/update`
- Resume: `POST /api/resume/upload`, `POST /api/resume/tailor`, `GET /api/resume/tailored`
- Candidate profile: `POST /api/candidate-profile/store`, `GET /api/candidate-profile/me`
- Jobs: `POST /api/jobs/discover`, `GET /api/jobs/me`, `PUT /api/jobs/{job_id}/status`
- Notifications: `GET /api/notifications`, `GET /api/email/history`, `POST /api/email/test`
- Settings: `GET/POST /api/settings/notifications`, `GET/POST /api/settings/application-mode`
- Limits: `GET /api/limits`, `GET /api/platform-limits`

## Email System

The backend uses a reusable Jinja2 email service with SMTP, HTML templates, plain-text fallback, retries, logs, and queue-friendly boundaries. Templates live in `backend/app/templates/email`.

Supported templates include welcome, verification, forgot password, password changed, resume ready, job matches, high match alerts, application updates, interview reminders, weekly reports, usage alerts, support acknowledgement, and account deletion.

## Daily Automation

Users can enable daily job search in `/settings/notifications`, choose a time/platforms, and fetch up to 20 jobs per platform per day. Manual refresh still works.

## Student Launch Notes

- New users are never auto-admin.
- Admin routes remain protected and hidden from the student dashboard.
- Use `backend/set_admin.py` later to promote a trusted account manually.
- Daily usage and platform limits are tracked per user and reset daily.

## Deployment Checklist

Use PostgreSQL, replace `JWT_SECRET`, set public API/CORS URLs, use n8n production `/webhook` URLs, configure SMTP, and keep `ENABLE_DEV_ADMIN_ROUTES=false`.

## Validation

```powershell
curl http://127.0.0.1:8001
cd frontend; npm run build
```
