# Collège Saint-Louis RAG Chatbot

Multilingual document chatbot powered by RAG (Retrieval-Augmented Generation) and ZhipuAI GLM models, with a modern web interface.

## Summary

This chatbot provides intelligent answers about Collège Saint-Louis by indexing school documents (newsletters, website content, PDFs) and using retrieval-augmented generation to provide accurate, contextual responses. The system supports French, English, and Chinese queries.

## Features

- **Multi-language support**: French, English, Chinese
- **Hybrid retrieval**: BM25 + vector search for accurate results
- **Web interface**: Modern Next.js chat UI
- **Admin panel**: Secure interface for content management (requires authentication)
- **Scheduled scraping**: Automatic content updates from school website
- **Performance monitoring**: Built-in metrics tracking

## Quick Start

### Prerequisites

- **Python 3.9+**
- **Node.js 22+**
- **npm 10+**
- **ZhipuAI API key**

### Option 1: Web Interface (Recommended)

```bash
# Start all services (frontend + backend)
./start.sh
```

Then visit:
- **Chat Interface**: http://localhost:3086
- **API Documentation**: http://localhost:8086/docs

### Option 2: CLI Only

#### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env with your ZhipuAI API key
```

Required environment variables:
- `AI_API_KEY`: Your ZhipuAI API key
- `AI_BASE_URL`: API base URL
- `AI_MODEL`: Model to use (GLM-4.7, glm-4-flash, etc.)

#### 2. Install Dependencies

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python api_server.py > ../logs/backend.log
```

**Frontend:**
```bash
cd frontend
npm install
```

#### 3. Run the CLI

```bash
# From project root
python3 run.py info
python3 run.py query --question "Your question here"

# From backend directory
cd backend
python3 -m src.cli info
python3 -m src.cli query --question "Your question here"
```

## Admin Panel

The admin panel provides secure access to system management features:

**Access:** http://localhost:8086/admin (requires authentication)

### Features

- **Content Status**: View indexed files, identify invalid documents
- **Crawler Management**:
  - Configure school URL for scraping
  - Set schedule time (default: 2 AM daily)
  - Trigger immediate scraping with progress tracking
- **File Upload**: Upload documents with automatic indexing
- **AI Configuration**: View and test AI provider connection
- **Performance Metrics**: Monitor system performance and query statistics

### Security

The admin panel is protected by:
- API key authentication (`INTERNAL_API_KEY`)
- Origin validation (`ALLOWED_ORIGINS`)
- Cloudflare Access (in production)

## Project Structure

```
chatbot/
├── backend/              # Python RAG backend
│   ├── src/             # Source modules
│   │   ├── milvus_rag.py  # RAG pipeline (Milvus version)
│   │   ├── cli.py         # CLI interface
│   │   └── ...            # Other modules
│   ├── data/            # Data files (Milvus indexes, inputs)
│   ├── api_server.py    # FastAPI server (port 8086)
│   └── requirements.txt  # Python dependencies
├── frontend/            # Next.js web interface
│   ├── app/            # Next.js App Router
│   ├── components/     # React components
│   └── package.json    # Node dependencies
├── docs/               # Documentation
├── start.sh            # Start both frontend and backend
├── stop.sh             # Stop all services
└── README.md           # This file
```

## Management Scripts

- **`./verify.sh`** - Verify project setup
- **`./start.sh`** - Start frontend and backend services
- **`./stop.sh`** - Stop all running services

## CLI Commands

- `info` - Display index statistics
- `query` - Query the knowledge base
- `index` - Index documents from data/input
- `clear` - Clear the index

## Testing

Run end-to-end tests:

```bash
cd backend
python3 tests/e2e/test_comprehensive.py
```

## Architecture

### System Architecture Diagram

For a comprehensive visual overview of the system architecture, see:
- **[System Architecture (Mermaid)](docs/diagrams/ARCHITECTURE.md)** - Mermaid diagram compatible with official @drawio/mcp
- **[Architecture Guide](docs/diagrams/ARCHITECTURE.md)** - Component descriptions and integration points
- **[Data Flow Diagram](docs/diagrams/DATA_FLOW.md)** - Complete query and indexing pipeline
- **[MCP Configuration](docs/diagrams/MCP_CONFIGURATION.md)** - Official @drawio/mcp setup and usage
- **[Quick Reference](docs/diagrams/QUICK_REFERENCE.md)** - Quick start guide and troubleshooting

### Frontend (Next.js)
- **Framework**: Next.js 15 with App Router
- **UI**: React 18 + Tailwind CSS
- **API Routes**: Proxy to Python backend
- **Port**: 3086

### Backend (Python)
- **API Server**: FastAPI (port 8086)
- **RAG System**: Hybrid retrieval (BM25 + Milvus vector search)
- **LLM**: ZhipuAI GLM models
- **Vector Database**: Milvus with HNSW indexing
- **Embeddings**: BAAI/bge-m3 (sentence-transformers)

### Data Flow

```
User → Next.js Frontend (3086)
    → API Route (/api/chat)
    → FastAPI Backend (8086)
    → RAG Pipeline (Milvus version)
    → Query Classification & Enhancement
    → Hybrid Retrieval (BM25 + Milvus Vector Search)
    → Context Building
    → LLM Generation (ZhipuAI GLM-4.7)
    → Confidence Scoring
    → Return Response
```

### System Components

**10 Major Layers:**
1. **Client Layer** - Web UI, Chat Interface, Admin Dashboard
2. **Frontend Layer** - Next.js 15, React Components, API Routes
3. **API Gateway** - Authentication and request proxying
4. **Backend API** - FastAPI REST endpoints and RAG orchestration
5. **Retrieval Layer** - Query classification, routing, and hybrid retrieval
6. **Vector Storage** - Milvus database with HNSW indexing for semantic search
7. **Data Processing** - Embeddings, semantic chunking, translation
8. **LLM Layer** - ZhipuAI GLM-4.7 API integration
9. **Document Indexing** - Ingestion, chunking, and embedding pipeline
10. **Monitoring** - Performance tracking, feedback collection, quality scoring

## Knowledge Base

The system currently indexes:
- **94 unique documents** (583 chunks)
- **24 PDF files** - Monthly newsletters (Info-parents)
- **70 text files** - Website content including school information, programs, activities, news

## License

MIT License - Copyright © 2025 Tony Xu

See [LICENSE](LICENSE) for details.

## Contact

Tony Xu <tony@tarch.ca>
