# EduChat Deployment Guide

## Option 1: Render + Supabase (Recommended)

### 1. Setup Supabase Database (Free)

1. Create account at [supabase.com](https://supabase.com)
2. Click "New Project"
3. Fill in details:
   - Name: `educhat`
   - Database Password: (create a strong password)
   - Region: (choose closest to your users)
4. Wait for setup to complete (~2 minutes)

5. **Get Connection Details:**
   - Go to Project Settings → Database
   - Find "Connection string" (URI)
   - It looks like: `postgresql://postgres:[password]@db.xxxx.supabase.co:5432/postgres`

6. **Environment Variables:**
   - `SUPABASE_URL`: `postgresql://postgres@db.xxxx.supabase.co`
   - `SUPABASE_KEY`: Your database password

### 2. Backend (Render)

1. Create account at [render.com](https://render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repo
4. Settings:
   - Name: `educhat-api`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python -m uvicorn api.index:app --host 0.0.0.0 --port $PORT`
5. Environment Variables:
   - `GEMINI_API_KEY`: Your Gemini API key
   - `SUPABASE_URL`: Your Supabase URL (from step 1)
   - `SUPABASE_KEY`: Your Supabase password
6. Click "Create Web Service"

### 3. Frontend (Render)

1. New → Static Site
2. Connect GitHub repo
3. Settings:
   - Name: `educhat-web`
   - Build: `npm run build`
   - Publish: `dist`

---

## Option 2: Vercel + Railway

### Frontend (Vercel - Free)
1. Go to [vercel.com](https://vercel.com)
2. Import GitHub repo
3. Deploy

### Backend (Railway - $5/month)
1. Go to [railway.app](https://railway.app)
2. New Project → "Deploy from GitHub repo"
3. Add Environment Variables:
   - `GEMINI_API_KEY`: Your key
   - `SUPABASE_URL`: Your Supabase URL
   - `SUPABASE_KEY`: Your Supabase password
4. Deploy

---

## Option 3: Fly.io (Free - No Sleep)

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch (in project folder)
fly launch

# Deploy
fly deploy
```

---

## Database Setup (Critical!)

### If Using Supabase:

1. **Create tables manually** (or the app will create them):
```sql
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    user TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lecture_notes (
    id SERIAL PRIMARY KEY,
    user TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    file_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

2. **Add Environment Variables** in your deployment platform:
   - `SUPABASE_URL`: From Supabase Dashboard → Settings → Database
   - `SUPABASE_KEY`: Your database password

---

## Update API URL in Code

Before deploying, update `main.js`:

```javascript
// Replace ALL instances of:
http://localhost:8000

// With your deployed backend URL:
https://educhat-api.onrender.com
```

---

## Required Files Created

| File | Purpose |
|------|---------|
| `Procfile` | Render backend startup |
| `runtime.txt` | Python 3.12 |
| `requirements.txt` | Python dependencies |
| `package.json` | Node scripts |
| `api/database.py` | SQLite + PostgreSQL support |

---

## Local Testing

```bash
# Backend
npm run server

# Frontend
npm run dev
```

Open http://localhost:5173

---

## Troubleshooting

**Database not connecting:**
- Check SUPABASE_URL format: `postgresql://postgres@db.xxx.supabase.co`
- Check SUPABASE_KEY is correct password

**App crashes:**
- Check Render logs for errors
- Verify all environment variables are set
- Ensure psycopg2-binary is installed