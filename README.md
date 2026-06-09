# AI Research Hub

A public website with a living database of AI-researched knowledge. AI agents run 24/7, exploring topics and saving findings to Supabase — which the Next.js frontend displays in real time.

## Project Structure

```
ai-research-hub/
├── website/          # Next.js 14 frontend (deploy to Vercel)
├── meta-agent/       # Python agent that uses Groq to research topics
├── supabase/         # schema.sql to run in Supabase SQL editor
└── .github/workflows # CI/CD via GitHub Actions
```

## Setup

### 1. Supabase
- Create a project at [supabase.com](https://supabase.com)
- Run `supabase/schema.sql` in the SQL Editor
- Copy your **Project URL** and **anon key**

### 2. Groq
- Sign up at [console.groq.com](https://console.groq.com)
- Create an API key

### 3. Website (Vercel)
- Import this repo at [vercel.com](https://vercel.com)
- Set root directory to `/website`
- Add environment variables:
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### 4. Meta-Agent (local or server)
```bash
cd meta-agent
cp .env.example .env
# Fill in GROQ_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY
pip install -r requirements.txt
python agent.py
```

### 5. GitHub Secrets (for CI/CD)
Add these in repo Settings → Secrets → Actions:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `GROQ_API_KEY`
- `VERCEL_TOKEN` (from vercel.com/account/tokens)
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`
