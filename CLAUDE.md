# CLAUDE.md

This file provides guidance for Claude Code when working with this project.

## Quick Navigation

- [AGENTS.md](AGENTS.md) - AI Agent guidelines
- [README](README.md) - Project overview and setup

## Project Overview

**College Saint-Louis RAG Chatbot** - A multilingual document Q&A system powered by retrieval-augmented generation and ZhipuAI GLM models.

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 15, React 18, TypeScript, Tailwind CSS |
| **Backend** | Python, FastAPI, Milvus |
| **LLM** | ZhipuAI GLM-4.7 |
| **Embeddings** | sentence-transformers (BAAI/bge-m3) |
| **Testing** | pytest (backend) |

## Project Structure

```
chatbot/
├── backend/              # Python RAG backend
│   ├── src/             # Core modules (milvus_rag.py, hybrid_retriever.py, etc.)
│   ├── tests/           # pytest tests
│   ├── api_server.py    # FastAPI server (port 8086)
│   └── requirements.txt # Python dependencies
├── frontend/            # Next.js web interface
│   ├── app/            # Next.js App Router
│   ├── components/     # React components
│   └── package.json    # Node dependencies
├── data/               # Shared data directory
├── docs/               # Documentation
├── .env                # Environment variables
├── start.sh            # Start both services
└── stop.sh             # Stop all services
```

## Core Principles

### 1. Language & Communication
- **Always respond in Chinese** (中文) for explanations and comments
- Keep technical terms (function names, APIs, etc.) in their original form

### 2. Testing
- Run `cd backend && pytest` before committing backend changes

### 3. Code Quality
- **Python**: Follow PEP 8, use type hints
- **TypeScript**: Use strict mode, avoid `any` types

## Running Services

| Command | Description |
|---------|-------------|
| `./start.sh` | Start frontend (3086) + backend (8086) |
| `./stop.sh` | Stop all services |
| `python3 run.py query --question "..."` | CLI query |

### Process Management Rules (CRITICAL)

**NEVER kill these processes:**
- **VSCode** - Never terminate the editor
- **Docker** - Never stop Docker containers or daemon
- **Main chatbot processes** - Only kill port-specific instances if needed

**Only kill when necessary:**
- Port 3086 (frontend dev server) - If restarting frontend
- Port 8086 (backend API server) - If restarting backend

**Safe restart commands:**
```bash
# To restart frontend only
pkill -f "next dev.*3086"

# To restart backend only
pkill -f "uvicorn.*8086"

# NEVER use: pkill -f "chatbot", pkill docker, etc.
```

## Configuration

Key environment variables (`.env`):

| Variable | Description |
|----------|-------------|
| `AI_API_KEY` | ZhipuAI API key |
| `AI_MODEL` | GLM model (default: GLM-4.7) |
| `AI_BASE_URL` | API base URL |
| `MILVUS_HOST` | Milvus host |
| `MILVUS_PORT` | Milvus port |
| `TOP_K` | Retrieval count (default: 10) |

## References

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Next.js Docs](https://nextjs.org/docs)
- [Milvus Docs](https://milvus.io/docs)
