# sUAS Intelligent Mission Planner

A professional-grade AI orchestration and deterministic physics engine for sUAS flight planning.
Includes LangGraph Conditional Edges and MemorySaver Checkpointers.

## Architecture
- **Frontend**: Next.js (App Router), TailwindCSS, React
- **Backend**: FastAPI, Python 3.11
- **Database**: PostgreSQL 15, SQLAlchemy
- **AI Orchestration**: LangGraph, LangChain, OpenAI
- **Deployment**: Docker Compose

## Quickstart (Local)
1. Rename `.env.example` to `.env` and add your `OPENAI_API_KEY`.
2. Run `docker-compose up --build`.
3. Open `http://localhost:3000` to access the Mission Control dashboard.
