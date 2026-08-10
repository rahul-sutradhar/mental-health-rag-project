# Serenity Mindspace / MindMate AI 🧘🤖

> A state-of-the-art mental wellness platform for students. Connects users with verified mental health specialists and a production-grade **AI Companion (MindMate)** powered by **FastAPI + Mistral AI (LLM & Embeddings & Reranker) + standard RAG + Argon2 + SQLite/Supabase PostgreSQL**.

---

## 🌟 Core Features

### 🤖 Mistral-Powered AI Companion
- **Standard RAG Pipeline**: Dynamically crawls and indexes wellness resources (`responses.json`) and FAQ pages (`faq.html`) into dense vector embeddings using Mistral's `mistral-embed` API.
- **Mistral Reranking**: Utilizes the official Mistral Reranker API (`mistral-rerank-latest`) to re-evaluate relevance scores and fetch the absolute best context chunks.
- **Structured JSON Mode**: Queries Mistral Large (`mistral-large-latest`) in structured JSON mode for real-time emotional analysis, risk levels, and empathetic responses.
- **ChatGPT-Style Multi-Threading**: Users can create, switch between, and delete chat threads. The AI automatically titles new chat threads dynamically based on the first message sent.
- **Permanent Chat Memory**: Chat history is persistently logged in the database per user session and thread.

### 🛡️ Modern Security & Tech Stack
- **FastAPI Backend**: Replaced Flask with a modern, high-performance, asynchronous FastAPI backend.
- **SQLAlchemy ORM**: Database-agnostic configuration that runs locally on **SQLite** (`mindmate.db`) with zero setup, and scales to **Supabase (PostgreSQL)** in production via a single `DATABASE_URL` environment variable.
- **Argon2 Password Hashing**: Utilizes `argon2-cffi` (winner of the Password Hashing Competition) to store password hashes securely.
- **Starlette Session Middleware**: Secure cookie-based login sessions.

### 🎨 Premium Dark UI
- Glassmorphic navigation headers, animated neon background accents, clean mobile-responsive drawer sidebar, token purchasing indicators, and self-care assessment pages.

---

## 📁 Repository Structure

The codebase is organized cleanly for both local development and instant deployment:

```text
Major_Project/
├── app.py                  ← FastAPI Backend Server & REST endpoints
├── bot.py                  ← Mistral RAG Engine (embeddings, reranking, completions)
├── responses.json          ← Structured Coping advice & Helplines (RAG source)
├── requirements.txt        ← Python Package dependencies
├── .env                    ← Environment variables configuration
├── .gitignore              ← Version control ignore files
├── static/                 ← Frontend CSS & JS assets
│   ├── css/
│   │   ├── main.css        ← Design tokens, reset, typography, dark mode
│   │   └── components.css  ← Component layouts (nav, cards, chat bubble layouts)
│   └── js/
│       └── utils.js        ← Helper functions (toasts, live clocks, crisis validation)
├── templates/              ← Flask/Jinja2 HTML templates (19 pages)
│   ├── index.html          ← Platform welcome page
│   ├── ai-chat.html        ← Multi-thread ChatGPT-style chat screen
│   ├── faq.html            ← App FAQ (RAG source)
│   └── ... (other pages)
└── trash/                  ← Legacy ML files, training datasets, and CLI test scripts
```

---

## 🚀 Local Installation & Setup

Follow these simple steps to run the application on your computer:

### 1. Prerequisite Packages
Make sure you have **Python 3.9+** installed.

### 2. Configure Environment Variables
Create a file named `.env` in the root folder and add your Mistral API key:
```env
MISTRAL_API_KEY=your_actual_mistral_api_key_here
SESSION_SECRET=some_random_secret_string_for_sessions
```
*(Optional)* For production deployment on Render, add your Supabase link:
```env
DATABASE_URL=postgresql://postgres.your_project:password@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

### 3. Install Dependencies
Open your command terminal in the project directory and run:
```bash
uv sync
```

### 4. Run the Server
Start the FastAPI server:
```bash
uv run python app.py
```
Open your browser and visit: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

---

## ⚡ Deployment Checklist (100% Free Production Tier)

To deploy this project to the cloud for free with persistent storage:

1. **Host Backend on Render**:
   - Create a Web Service on Render connecting to your GitHub repo.
   - Set the runtime to `Python` and the build command to `pip install -r requirements.txt`.
   - Set the start command to `uvicorn app:app --host 0.0.0.0 --port $PORT`.

2. **Host Database on Supabase**:
   - Create a free project on Supabase.
   - Go to Project Settings → Database → Connection Strings (Transaction mode) and copy the URL.

3. **Add Environment Variables**:
   - In your Render Web Service dashboard, add variables:
     - `MISTRAL_API_KEY`: *(Your Mistral API key)*
     - `DATABASE_URL`: *(Your Supabase connection string)*
     - `SESSION_SECRET`: *(A random hash)*
   - When Render boots, SQLAlchemy will automatically detect Supabase and build the tables instantly!

---

## 🇮🇳 India-Specific Crisis Resources

MindMate is a support companion, not a replacement for psychiatric emergency services. If you or someone you know is in distress, please contact:

- **Emergency Response**: Call **112** (24/7)
- **Vandrevala Foundation**: Call **1860-2662-345** (24/7, free)
- **iCall (TISS)**: Call **9152987821** (Monday–Saturday, 8 AM–10 PM)
- **AASRA**: Call **9820466567** (24/7)
