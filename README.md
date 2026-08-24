# THREAD AI

THREAD AI is a contextual AI interaction platform built around one idea:

Ask where the doubt happens.

Users ask an AI question, receive a full answer, highlight any exact word/phrase/sentence inside that answer, and open a contextual thread attached to that selected text. THREAD AI also includes a prompt enhancer for turning rough questions into clearer prompts before asking.

## Architecture

- Frontend: Vite + React, single-page app with lightweight route handling.
- Backend: FastAPI, Pydantic, SQLAlchemy.
- Auth: Backend-owned Google OAuth with HttpOnly signed session cookies.
- LLM: Gemini by default, Groq supported through the provider abstraction.
- Local database: SQLite.
- Production database: PostgreSQL recommended.
- Deployment targets: Vercel for frontend, Render for backend/Postgres.

## Routes

- `/` sign-in and product welcome page.
- `/app` protected THREAD AI chatbot.
- `/terms` placeholder Terms page.
- `/privacy` placeholder Privacy page.

## Backend API

- `GET /api/health`
- `GET /api/auth/config`
- `GET /api/auth/me`
- `GET /api/auth/google/start`
- `GET /api/auth/google/callback`
- `POST /api/auth/logout`
- `POST /api/chat`
- `POST /api/enhance-prompt`
- `POST /api/threads`
- `POST /api/threads/{thread_id}/messages`
- `GET /api/threads/{thread_id}`
- `GET /api/responses/{response_id}/threads`

Chat, prompt enhancement, and thread endpoints require a valid session cookie.

## Local Setup

```bash
cd "C:\Users\siddh\OneDrive\Documents\New project\THREAD AI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Frontend:

```bash
cd "C:\Users\siddh\OneDrive\Documents\New project\THREAD AI\frontend"
npm install
copy .env.example .env
```

Set `frontend\.env`:

```env
VITE_API_BASE=http://127.0.0.1:8020
```

## Environment Variables

Backend `.env`:

```env
LLM_PROVIDER=auto
GEMINI_API_KEY=
GEMINI_MODEL_NAME=gemini-3.5-flash-lite
GROQ_API_KEY=
MODEL_NAME=llama-3.1-8b-instant
DATABASE_URL=sqlite:///./thread_ai.db
FRONTEND_ORIGIN=http://127.0.0.1:4173
FRONTEND_URL=http://127.0.0.1:4173
BACKEND_URL=http://127.0.0.1:8020
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AUTH_SECRET=
COOKIE_SECURE=false
SESSION_DAYS=14
ALLOW_DEV_AUTH=true
```

Generate a strong `AUTH_SECRET` before using Google sign-in:

```powershell
[Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

## Google OAuth Setup

1. Open Google Cloud Console.
2. Create or select a project.
3. Configure the OAuth consent screen.
4. Create OAuth Client ID credentials for a Web application.
5. Add authorized JavaScript origins:
   - `http://127.0.0.1:4173`
   - `http://localhost:5173`
   - your production frontend URL
6. Add authorized redirect URIs:
   - `http://127.0.0.1:8020/api/auth/google/callback`
   - your production backend URL plus `/api/auth/google/callback`
7. Put the client ID and client secret in backend `.env`.

Do not put `GOOGLE_CLIENT_SECRET` in frontend environment variables.

## Running Locally

Backend:

```bash
cd "C:\Users\siddh\OneDrive\Documents\New project\THREAD AI"
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8020
```

Frontend production preview:

```bash
cd "C:\Users\siddh\OneDrive\Documents\New project\THREAD AI\frontend"
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173`.

## Production Build

Frontend:

```bash
cd frontend
npm install
npm run build
```

Backend:

```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Deployment

Recommended simple deployment:

- Vercel for `frontend`
- Render for FastAPI backend and managed PostgreSQL

Backend on Render:

1. Use `render.yaml`.
2. Set secret env vars:
   - `GEMINI_API_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `FRONTEND_URL`
   - `FRONTEND_ORIGIN`
   - `BACKEND_URL`
3. Keep `COOKIE_SECURE=true`.
4. Keep `ALLOW_DEV_AUTH=false` in production.
5. Use Render PostgreSQL for `DATABASE_URL`.

Frontend on Vercel:

1. Set project root to `frontend`.
2. Set `VITE_API_BASE` to the deployed backend URL.
3. Deploy.

After both deployments, update Google OAuth allowed origins and callback URLs to match production.

## Security Notes

- Sessions are signed server-side and stored in HttpOnly cookies.
- Google ID tokens are verified through Google token verification.
- Conversations are associated with authenticated users.
- Thread reads/writes are checked against the owning conversation user.
- `.env`, database files, and frontend local env files are ignored by Git.

## Tests

```bash
cd "C:\Users\siddh\OneDrive\Documents\New project\THREAD AI"
.\.venv\Scripts\Activate.ps1
python -m pytest
```

## Known Limitations

- Email sign-in UI is present but needs an email provider before it can send magic links.
- Legal pages are placeholders and should be reviewed before launch.
- Existing local SQLite rows created before auth may not be visible because new conversations are user-owned.
- OAuth cannot be fully tested until real Google OAuth credentials are added.
- No streaming responses yet.
