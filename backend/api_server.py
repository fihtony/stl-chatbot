#!/usr/bin/env python3
"""FastAPI server for the chatbot backend."""

import sys
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import threading
import logging
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import uuid
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config
from src.embedding import EmbeddingClient
from src.zhipuai_llm import ZhipuAIClient
from src.milvus_store import MilvusStore
from src.milvus_indexer import MilvusIndexer
from src.document_registry import DocumentRegistry
from src.translation_service import FreeTranslationService
from src.milvus_rag import MilvusRAGPipeline, detect_language
from src.performance_monitor import PerformanceMonitor

# Setup logging
# Ensure logs directory exists at project root
import os
# Get the project root (parent of backend directory)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "scraping.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

# Import indexing functions
from api_indexing import (
    index_files,
    index_new_files_only,
    rebuild_index_full,
    verify_index,
    IndexFilesRequest,
    index_progress,
)

# Initialize FastAPI app
app = FastAPI(title="Chatbot API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3086", "http://localhost:8086"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Milvus store and indexer for document upload
milvus_store: Optional[MilvusStore] = None
milvus_indexer: Optional[MilvusIndexer] = None
document_registry: Optional[DocumentRegistry] = None

# Milvus RAG pipeline instance
milvus_rag: Optional[MilvusRAGPipeline] = None

# Global performance monitor for tracking query metrics
performance_monitor = PerformanceMonitor()

# ============== Scrape Status Management ==============
class ScrapeStatus:
    """Scrape status manager."""

    def __init__(self):
        self.is_running: bool = False
        self.start_time: Optional[float] = None
        self.current_page: str = ""
        self.total_pages: int = 0
        self.downloaded_pdfs: int = 0
        self.total_pdfs: int = 0
        self.new_pages: int = 0  # New pages scraped in this run
        self.new_documents: int = 0  # New documents downloaded in this run
        self.last_run: Optional[str] = None
        self.error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "start_time": self.start_time,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "downloaded_pdfs": self.downloaded_pdfs,
            "total_pdfs": self.total_pdfs,
            "new_pages": self.new_pages,
            "new_documents": self.new_documents,
            "last_run": self.last_run,
            "error_message": self.error_message
        }

scrape_status = ScrapeStatus()

# ============== Scrape Configuration ==============
from src.scrape_config import ScrapeConfig

scrape_config = ScrapeConfig.load()  # Loads from JSON or defaults

# ============== Scheduler ==============
scheduler_logger = logging.getLogger(__name__)
scheduler = None  # Will be initialized in startup_event


def update_scheduler():
    """Update or create the scheduler job based on current config."""
    global scheduler

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    # If scheduler exists, shut it down
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
            scheduler_logger.info("Previous scheduler shut down")
        except Exception as e:
            scheduler_logger.error(f"Error shutting down scheduler: {e}")

    # Only create scheduler if enabled
    if not scrape_config.schedule_enabled:
        scheduler_logger.info("Scheduler is disabled in config")
        scheduler = None
        return

    try:
        scheduler = BackgroundScheduler(daemon=True)

        # Parse schedule_time (HH:MM format)
        hour, minute = scrape_config.schedule_time.split(':')
        hour = int(hour)
        minute = int(minute)

        # Add job that runs at specified time daily
        scheduler.add_job(
            scheduled_scrape_trigger,
            CronTrigger(hour=hour, minute=minute),
            id='daily_scrape',
            name='Daily website scraping',
            max_instances=1  # Only one instance at a time
        )

        scheduler.start()
        scheduler_logger.info(f"Scheduler started: daily scraping at {scrape_config.schedule_time}")
    except Exception as e:
        scheduler_logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        scheduler = None


def scheduled_scrape_trigger():
    """Trigger scrape from scheduler - checks if already running first."""
    global scrape_status

    scheduler_logger.info("Scheduler triggered scrape check")

    # Check if scraping is already running
    if scrape_status.is_running:
        scheduler_logger.info("Scheduler skipped: scrape already running")
        return

    scheduler_logger.info(f"Scheduler starting scrape from {scrape_config.school_url}")

    # Run scrape in background thread with trigger source
    thread = threading.Thread(target=run_scrape_in_background, args=("scheduler",), daemon=True, name="ScheduledScrape")
    thread.start()

    scheduler_logger.info("Scheduler started scrape thread")

# ============== Content Analysis Functions ==============
def get_content_status() -> Dict[str, Any]:
    """Analyze and return content status."""
    scraped_dir = Path("./data/input/scraped")
    pdfs_dir = scraped_dir / "pdfs"
    pages_dir = scraped_dir / "pages"
    
    # Count valid trunked files (non-empty text files with significant content)
    valid_trunked_files = []
    invalid_files = []
    
    if pages_dir.exists():
        for txt_file in pages_dir.glob("*.txt"):
            try:
                content = txt_file.read_text(encoding='utf-8')
                # A valid trunked file should have meaningful content (>100 chars)
                if len(content) > 100:
                    valid_trunked_files.append({
                        "name": txt_file.name,
                        "size": len(content),
                        "path": str(txt_file.relative_to("."))
                    })
                else:
                    invalid_files.append({
                        "name": txt_file.name,
                        "size": len(content),
                        "path": str(txt_file.relative_to(".")),
                        "reason": "Empty or too small"
                    })
            except Exception as e:
                invalid_files.append({
                    "name": txt_file.name,
                    "size": 0,
                    "path": str(txt_file.relative_to(".")),
                    "reason": str(e)
                })
    
    # Count PDFs
    pdf_count = 0
    pdf_files = []
    if pdfs_dir.exists():
        for pdf_file in pdfs_dir.glob("*.pdf"):
            try:
                size = pdf_file.stat().st_size
                if size > 0:
                    pdf_count += 1
                    pdf_files.append({
                        "name": pdf_file.name,
                        "size": size,
                        "path": str(pdf_file.relative_to("."))
                    })
            except Exception:
                pass
    
    return {
        "total_trunked_files": len(valid_trunked_files),
        "total_invalid_files": len(invalid_files),
        "total_pdfs": pdf_count,
        "valid_trunked_files": valid_trunked_files[:50],
        "invalid_files": invalid_files[:20],
        "pdf_files": pdf_files,  # Show all PDFs, not truncated
        "scraped_dir": str(scraped_dir.resolve()),
        "analyzed_at": datetime.now().isoformat()
    }


# ============== Scrape Trigger Function ==============
# Browser-like headers to avoid 403 Forbidden errors
SCRAPER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def run_scrape_in_background(trigger_source: str = "unknown"):
    """Run scrape in background thread with proper error handling and logging.

    Args:
        trigger_source: Source of the trigger - 'manual', 'scheduler', or 'unknown'
    """
    global scrape_status

    import logging
    logger = logging.getLogger(__name__)

    try:
        import requests
        from bs4 import BeautifulSoup
        from bs4.exceptions import ParserRejectedMarkup
        from urllib.parse import urljoin, urlparse
        import re

        # Check if already running (concurrent prevention)
        if scrape_status.is_running:
            logger.info(f"[{trigger_source.upper()}] Scraping already in progress, skipping request")
            return

        logger.info(f"[{trigger_source.upper()}] Starting scrape from {scrape_config.school_url}")
        scrape_status.is_running = True
        scrape_status.start_time = int(time.time())  # Unix timestamp in seconds
        scrape_status.error_message = ""
        scrape_status.total_pages = 0
        scrape_status.downloaded_pdfs = 0
        scrape_status.total_pdfs = 0
        scrape_status.new_pages = 0
        scrape_status.new_documents = 0

        base_url = scrape_config.school_url
        output_dir = Path(scrape_config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pages_dir = output_dir / "pages"
        docs_dir = output_dir / "documents"
        pages_dir.mkdir(exist_ok=True)
        docs_dir.mkdir(exist_ok=True)

        # Track existing files to count new ones
        existing_pages = set(f.stem for f in pages_dir.glob("*.txt")) if pages_dir.exists() else set()
        existing_docs = set(f.stem for f in docs_dir.glob("*.pdf")) if docs_dir.exists() else set()
        logger.info(f"Found {len(existing_pages)} existing pages, {len(existing_docs)} existing documents")

        visited = set()
        queue = [base_url]
        pdf_urls = []

        page_count = 0
        consecutive_404_count = 0  # Track consecutive 404 errors
        MAX_CONSECUTIVE_404 = 3    # Stop after 3 consecutive 404s

        logger.info("Starting page crawling...")

        while queue and page_count < 100:
            # Check if stop was requested
            if not scrape_status.is_running:
                logger.info("Scrape stop requested, exiting crawling loop")
                break

            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            if any(skip in url for skip in ['/wp-json/', '/xmlrpc.php', '/feed/']):
                continue

            scrape_status.current_page = url
            logger.info(f"Crawling ({page_count + 1}): {url}")

            try:
                response = requests.get(url, headers=SCRAPER_HEADERS, timeout=scrape_config.timeout)

                # Check for 404 specifically
                if response.status_code == 404:
                    consecutive_404_count += 1
                    logger.warning(f"404 Not Found: {url} (consecutive 404s: {consecutive_404_count}/{MAX_CONSECUTIVE_404})")
                    scrape_status.error_message = f"404 at {url} ({consecutive_404_count}/{MAX_CONSECUTIVE_404})"

                    # Stop after MAX_CONSECUTIVE_404 consecutive 404s
                    if consecutive_404_count >= MAX_CONSECUTIVE_404:
                        logger.info(f"Reached {MAX_CONSECUTIVE_404} consecutive 404s, stopping crawl")
                        break
                    continue
                elif response.status_code == 403:
                    consecutive_404_count += 1
                    logger.warning(f"403 Forbidden: {url}")
                    scrape_status.error_message = f"403 at {url}"
                    if consecutive_404_count >= MAX_CONSECUTIVE_404:
                        logger.info("Too many access errors, stopping crawl")
                        break
                    continue

                # Reset 404 counter on successful request
                consecutive_404_count = 0
                response.raise_for_status()
                html = response.text

            except requests.exceptions.Timeout:
                consecutive_404_count += 1
                logger.warning(f"Timeout: {url}")
                scrape_status.error_message = f"Timeout at {url}"
                if consecutive_404_count >= MAX_CONSECUTIVE_404:
                    logger.info("Too many timeouts, stopping crawl")
                    break
                continue
            except Exception as e:
                consecutive_404_count += 1
                logger.error(f"Error fetching {url}: {e}")
                scrape_status.error_message = f"Error: {e}"
                if consecutive_404_count >= MAX_CONSECUTIVE_404:
                    logger.info("Too many errors, stopping crawl")
                    break
                continue

            # Parse HTML with fallback parsers for malformed markup
            soup = None
            parse_errors = []

            for parser in ['html.parser', 'html5lib', 'lxml']:
                try:
                    soup = BeautifulSoup(html, parser)
                    logger.debug(f"Successfully parsed {url} with {parser}")
                    break  # Success, use this parser
                except ParserRejectedMarkup as e:
                    parse_errors.append(f"{parser}: {str(e)[:100]}")
                    logger.debug(f"Parser {parser} rejected markup for {url}: {str(e)[:100]}")
                    continue
                except Exception as e:
                    parse_errors.append(f"{parser}: {str(e)[:100]}")
                    logger.debug(f"Parser {parser} failed for {url}: {str(e)[:100]}")
                    continue

            if soup is None:
                # All parsers failed - log and skip this page
                error_detail = "; ".join(parse_errors)
                logger.warning(f"All parsers failed for {url}. Errors: {error_detail}")
                scrape_status.error_message = f"Parse error: Unable to parse page content (skipped)"
                # Don't count parse errors as consecutive errors - it's a content issue, not network/server
                # Just skip to the next page
                continue
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            content = soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            if not path:
                page_name = "homepage"
            else:
                page_name = re.sub(r'\.\w+$', '', path).replace('/', '_')
                page_name = re.sub(r'[^\w\-_]', '_', page_name)[:100]
            
            if page_name:
                page_file = pages_dir / f"{page_name}.txt"
                is_new_page = page_name not in existing_pages
                with open(page_file, 'w', encoding='utf-8') as f:
                    f.write(f"URL: {url}\n\n")
                    f.write(f"{'=' * 80}\n\n")
                    f.write('\n'.join(lines))
                page_count += 1
                scrape_status.total_pages = page_count
                if is_new_page:
                    scrape_status.new_pages += 1
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                absolute_url = urljoin(url, href)
                if urlparse(absolute_url).netloc == urlparse(base_url).netloc:
                    if absolute_url not in visited and absolute_url not in queue:
                        queue.append(absolute_url)
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '.pdf' in href.lower():
                    pdf_url = urljoin(url, href)
                    if pdf_url not in pdf_urls:
                        pdf_urls.append(pdf_url)
            
            time.sleep(0.3)
        
        scrape_status.total_pdfs = len(pdf_urls)
        downloaded = 0

        logger.info(f"Found {len(pdf_urls)} PDF URLs, downloading up to 10...")

        for i, pdf_url in enumerate(pdf_urls[:10]):
            # Check if stop was requested
            if not scrape_status.is_running:
                logger.info("Scrape stop requested during PDF download, exiting")
                break

            try:
                logger.info(f"Downloading PDF {i+1}/{min(10, len(pdf_urls))}: {pdf_url}")
                response = requests.get(pdf_url, headers=SCRAPER_HEADERS, timeout=scrape_config.timeout)
                response.raise_for_status()

                # Extract filename from URL, stripping query parameters
                filename = pdf_url.split('/')[-1].split('?')[0]
                if not filename or len(filename) > 200:
                    filename = f"document_{hash(pdf_url) % 10000}.pdf"

                # Get filename stem (without extension) for checking if new
                filename_stem = Path(filename).stem
                is_new_doc = filename_stem not in existing_docs

                pdf_path = docs_dir / filename
                with open(pdf_path, 'wb') as f:
                    f.write(response.content)
                downloaded += 1
                scrape_status.downloaded_pdfs = downloaded
                if is_new_doc:
                    scrape_status.new_documents += 1
                logger.info(f"Downloaded: {filename} ({'new' if is_new_doc else 'existing'})")
            except Exception as e:
                logger.warning(f"Failed to download PDF {pdf_url}: {e}")

            time.sleep(0.5)

        scrape_status.last_run = datetime.now().isoformat()

        # Log final summary
        logger.info(f"Scraping complete: {page_count} pages, {downloaded} PDFs downloaded")

        # Auto-index new files after scraping completes
        try:
            logger.info("Auto-indexing new files with Milvus...")
            # Use Milvus indexer
            from src.milvus_store import MilvusStore
            from src.milvus_indexer import MilvusIndexer

            milvus_store = MilvusStore(
                host=config.milvus_host,
                port=config.milvus_port,
                collection_name=config.milvus_collection,
                reset=False,
            )
            from src.milvus_indexer import MilvusIndexer
            # Use embedding model string (MilvusIndexer initializes EmbeddingClient internally)
            indexer = MilvusIndexer(
                milvus_store,
                embedding_model="BAAI/bge-m3",
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap
            )

            index_result = indexer.add_new_documents(input_dir=scrape_config.output_dir)

            if index_result.get("chunks_added", 0) > 0:
                logger.info(f"Auto-indexed {index_result.get('chunks_added', 0)} chunks from {index_result.get('added', 0)} files")
                scrape_status.error_message = f"Done: {page_count} pages, {downloaded} PDFs, {index_result.get('chunks_added', 0)} chunks indexed"
            else:
                # No new files or all were duplicates
                logger.info(f"Processed {index_result.get('added', 0)} files but no new chunks (duplicate content)")
                scrape_status.error_message = f"Done: {page_count} pages, {downloaded} PDFs"
        except Exception as idx_error:
            logger.error(f"Auto-indexing failed: {idx_error}", exc_info=True)
            scrape_status.error_message = f"Done: {page_count} pages, {downloaded} PDFs (index error: {str(idx_error)[:80]})"

    except Exception as e:
        logger.error(f"Scraping error: {e}", exc_info=True)
        scrape_status.error_message = f"Error: {str(e)}"
    finally:
        scrape_status.is_running = False
        scrape_status.current_page = ""
        logger.info("Scraping process ended")


# ============== Pydantic Models ==============
class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    provider: str = "zhipu"
    useCache: bool = True
    useFAQ: bool = True
    searchMethod: str = "hybrid"
    enableSubjectFilter: bool = True
    enableQueryExpansion: bool = True
    use_milvus: bool = True


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    provider: str
    metadata: Dict[str, Any]


class ScrapeConfigRequest(BaseModel):
    """Scrape configuration request model."""
    school_url: Optional[str] = None
    schedule_enabled: Optional[bool] = None
    schedule_time: Optional[str] = None
    output_dir: Optional[str] = None
    timeout: Optional[int] = None
    respect_robots_txt: Optional[bool] = None


class AITestRequest(BaseModel):
    """AI test request model."""
    provider: str = "zhipu"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    test_message: str = "Hello, please respond with 'OK' if you can read this message."


def initialize_milvus_rag():
    """Initialize the Milvus RAG pipeline."""
    global milvus_rag

    if milvus_rag is not None:
        return milvus_rag

    print("🚀 Initializing Milvus RAG pipeline...")

    try:
        # Initialize Milvus store
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )

        # Initialize embedding client - MUST use BGE-M3 for Milvus (1024 dim)
        embedding_client = EmbeddingClient(
            model_name="BAAI/bge-m3",  # Must match Milvus collection schema
            device=config.embedding_device
        )

        # Initialize LLM client
        llm_client = ZhipuAIClient(
            api_key=config.ai_api_key,
            base_url=config.ai_base_url,
            model=config.ai_model,
            timeout=120,
        )

        # Initialize translation service
        translation_service = FreeTranslationService(llm_client=llm_client)

        # Initialize Milvus RAG pipeline
        milvus_rag = MilvusRAGPipeline(
            milvus_store=milvus_store,
            embedding_client=embedding_client,
            llm_client=llm_client,
            translation_service=translation_service,
            top_k=10,
        )

        print("✅ Milvus RAG pipeline initialized successfully")
        return milvus_rag

    except Exception as e:
        print(f"❌ Failed to initialize Milvus RAG pipeline: {e}")
        return None


def initialize_milvus_components():
    """Initialize Milvus store, indexer, and document registry."""
    global milvus_store, milvus_indexer, document_registry

    if milvus_store is not None and milvus_indexer is not None and document_registry is not None:
        return milvus_store, milvus_indexer, document_registry

    print("🚀 Initializing Milvus components...")

    try:
        # Initialize Milvus store
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,  # Don't reset existing collection
        )
        print("✅ Milvus store initialized")

        # Initialize Milvus indexer
        # Always use BGE-M3 for Milvus operations (1024 dimensions)
        milvus_indexer = MilvusIndexer(
            milvus_store=milvus_store,
            embedding_model="BAAI/bge-m3",  # Fixed to match Milvus collection schema
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )
        print("✅ Milvus indexer initialized (using BAAI/bge-m3)")

        # Initialize document registry
        document_registry = DocumentRegistry()
        print("✅ Document registry initialized")

        return milvus_store, milvus_indexer, document_registry

    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize Milvus components: {e}")
        print("   Document upload functionality will be limited")
        return None, None, None


def get_upload_dir() -> Path:
    """获取上传文件保存目录。"""
    upload_dir = Path(__file__).parent.parent / "data" / "input" / "uploaded"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@app.on_event("startup")
async def startup_event():
    """Initialize Milvus RAG pipeline, Milvus components, and scheduler on startup."""
    global milvus_rag, milvus_store, milvus_indexer, document_registry
    try:
        print("🔄 Starting Milvus RAG pipeline initialization...")
        initialize_milvus_rag()
        if milvus_rag:
            print("🔄 Preloading embedding model...")
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: milvus_rag.milvus_store.health_check()
                )
                print("✅ Embedding model preloaded successfully")
            except Exception as e:
                print(f"⚠️ Warning: Could not preload model: {e}")
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize Milvus RAG on startup: {e}")
        print("   Pipeline will be initialized on first request")

    # Initialize Milvus components for document upload
    try:
        print("🔄 Initializing Milvus components...")
        if milvus_store is None or milvus_indexer is None or document_registry is None:
            initialize_milvus_components()
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize Milvus components on startup: {e}")

    # Initialize scheduler
    try:
        print("🔄 Initializing scheduler...")
        update_scheduler()
        if scheduler:
            print(f"✅ Scheduler enabled: daily scraping at {scrape_config.schedule_time}")
        else:
            print("ℹ️ Scheduler disabled")
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize scheduler: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on server shutdown."""
    global scheduler
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
            print("🔄 Scheduler shut down")
        except Exception as e:
            print(f"⚠️ Error shutting down scheduler: {e}")


# ============== Basic Endpoints ==============
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Chatbot API Server",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Milvus RAG system."""
    # Check Milvus health
    milvus_healthy = False
    milvus_count = 0
    if milvus_store is not None:
        try:
            milvus_health = milvus_store.health_check()
            milvus_healthy = milvus_health.get("healthy", False)
            milvus_count = milvus_health.get("count", 0)
        except:
            milvus_healthy = False

    # LLM health is assumed healthy if we can reach the health endpoint
    # The actual LLM is created on-demand per request
    llm_healthy = True

    return {
        "status": "healthy" if milvus_healthy and llm_healthy else "degraded",
        "milvus_rag_initialized": milvus_rag is not None,
        "milvus_healthy": milvus_healthy,
        "llm_healthy": llm_healthy,
        "document_count": milvus_count,
        "vector_database": "Milvus",
        "semantic_search": "Enabled (HNSW + COSINE)",
    }


@app.get("/api/chat")
async def chat_get():
    """GET endpoint for chat - returns API info."""
    return {
        "endpoint": "/api/chat",
        "version": "2.0",
        "methods": ["POST", "GET"],
        "features": {
            "semantic_search": "Milvus (HNSW + COSINE)",
            "embedding_model": "BAAI/bge-m3 (1024 dim)",
            "multi_language": "French, English, Chinese",
            "auto_translation": "English to French",
            "school_terms_expansion": "Collège Saint-Louis specific",
        },
        "usage": {
            "post": {
                "summary": "Send a chat message",
                "body": {
                    "message": "Your question",
                }
            }
        }
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat_post(request: ChatRequest):
    """POST endpoint for chat."""
    global milvus_rag, performance_monitor

    try:
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message is required")

        # Track start time for performance monitoring
        start_time = time.time()

        print(f"\n{'='*80}")
        print(f"📨 Received chat request: {request.message[:100]}...")

        # Detect language for performance tracking
        language = detect_language(request.message)

        # Initialize Milvus RAG if needed
        if milvus_rag is None:
            print("⚠️ Milvus RAG not initialized, initializing now...")
            initialize_milvus_rag()
            if milvus_rag is None:
                raise HTTPException(
                    status_code=503,
                    detail="Milvus RAG is not available. Please ensure Milvus is running and try again."
                )

        print("🔍 Using Milvus RAG pipeline")
        path_type = "milvus_path"
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: milvus_rag.query(request.message)
        )

        print(f"✅ Response generated successfully (Milvus RAG)")
        print(f"{'='*80}\n")

        # Record performance metrics
        elapsed_ms = (time.time() - start_time) * 1000
        performance_monitor.record_query_simple(language, path_type, elapsed_ms)

        return ChatResponse(
            response=result["answer"],
            provider=request.provider,
            metadata={
                "method": "milvus",
                "cached": False,
                "faq": False,
                "chunksUsed": len(result.get("sources", [])),
                "timing": {
                    "total": result.get("metadata", {}).get("total_time", 0)
                }
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ Error processing chat request: {e}")
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Admin API Endpoints ==============

@app.get("/api/admin/content-status")
async def get_content_status_endpoint():
    """
    GET /api/admin/content-status
    Returns the status of downloaded content including valid trunked files,
    invalid files, and PDF files.
    """
    try:
        status = get_content_status()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/scrape-status")
async def get_scrape_status_endpoint():
    """
    GET /api/admin/scrape-status
    Returns the current scrape/crawler status including whether it's running,
    current page being scraped, and download statistics.
    """
    try:
        status = scrape_status.to_dict()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/scrape-config")
async def get_scrape_config_endpoint():
    """
    GET /api/admin/scrape-config
    Returns the current scrape configuration including school URL,
    schedule time, and enabled status.
    """
    try:
        cfg = scrape_config.to_dict()
        return {
            "success": True,
            "data": cfg
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/scrape-config")
async def set_scrape_config_endpoint(request: ScrapeConfigRequest):
    """
    POST /api/admin/scrape-config
    Sets the scrape configuration including school URL, schedule time, etc.
    Updates scheduler if schedule settings change.
    """
    try:
        # Track if schedule settings changed
        schedule_changed = (
            (request.schedule_enabled is not None and request.schedule_enabled != scrape_config.schedule_enabled) or
            (request.schedule_time is not None and request.schedule_time != scrape_config.schedule_time)
        )

        if request.school_url is not None:
            scrape_config.school_url = request.school_url
        if request.schedule_enabled is not None:
            scrape_config.schedule_enabled = request.schedule_enabled
        if request.schedule_time is not None:
            scrape_config.schedule_time = request.schedule_time
        if request.output_dir is not None:
            scrape_config.output_dir = request.output_dir
        if request.timeout is not None:
            scrape_config.timeout = request.timeout
        if request.respect_robots_txt is not None:
            scrape_config.respect_robots_txt = request.respect_robots_txt

        # Save to JSON file
        if not scrape_config.save():
            return {
                "success": False,
                "message": "Configuration updated but failed to persist to disk",
                "data": scrape_config.to_dict()
            }

        # Update scheduler if schedule settings changed
        if schedule_changed:
            scheduler_logger.info(f"Schedule settings changed, updating scheduler (enabled={scrape_config.schedule_enabled}, time={scrape_config.schedule_time})")
            update_scheduler()

        return {
            "success": True,
            "message": "Configuration saved" + (f", scheduler updated to run at {scrape_config.schedule_time}" if scrape_config.schedule_enabled else ", scheduler disabled"),
            "data": scrape_config.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/scheduler-status")
async def get_scheduler_status():
    """
    GET /api/admin/scheduler-status
    Returns the current scheduler status and next scheduled run time.
    """
    try:
        from datetime import datetime, timedelta

        next_run_time = None
        if scheduler and scheduler.running:
            jobs = scheduler.get_jobs()
            if jobs:
                job = jobs[0]
                next_run = job.next_run_time
                if next_run:
                    next_run_time = next_run.isoformat()

        # Determine last run status for Completed/Error states
        last_run_status = None
        if scrape_status.last_run:
            try:
                last_run_time = datetime.fromisoformat(scrape_status.last_run)
                now = datetime.now()
                time_since_last_run = (now - last_run_time).total_seconds()

                # Check if last run was successful (no error or error is just a 404 warning)
                is_successful = not scrape_status.is_running  # Completed if not running
                has_error = scrape_status.error_message and not scrape_status.error_message.startswith("404") and not scrape_status.error_message.startswith("Done:")

                if time_since_last_run < 3600 and is_successful:  # Within 1 hour
                    last_run_status = "completed"
                elif time_since_last_run < 3600 and has_error:
                    last_run_status = "error"
            except:
                pass

        # Format last run time for display
        from src.date_utils import format_iso_datetime
        last_run_time_str = format_iso_datetime(scrape_status.last_run) if scrape_status.last_run else None

        return {
            "success": True,
            "data": {
                "enabled": scrape_config.schedule_enabled,
                "schedule_time": scrape_config.schedule_time,
                "running": scheduler is not None and scheduler.running,
                "next_run": next_run_time,
                "jobs": len(scheduler.get_jobs()) if scheduler else 0,
                "last_run_status": last_run_status,  # "completed" or "error" or null
                "last_run_time": last_run_time_str  # Formatted timestamp or null
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/scrape-trigger")
async def trigger_scrape_endpoint():
    """
    POST /api/admin/scrape-trigger
    Immediately triggers a scrape operation (runs in background).
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        if scrape_status.is_running:
            logger.info("Scrape trigger rejected: already running")
            raise HTTPException(status_code=409, detail="Scrape is already running")

        logger.info(f"Scrape triggered manually from {scrape_config.school_url}")

        thread = threading.Thread(target=run_scrape_in_background, args=("manual",), daemon=True)
        thread.start()

        return {
            "success": True,
            "message": "Scrape triggered successfully",
            "data": {
                "is_running": True,
                "start_time": int(time.time())
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering scrape: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/scrape-stop")
async def stop_scrape_endpoint():
    """
    POST /api/admin/scrape-stop
    Stops any currently running scrape operation.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        if not scrape_status.is_running:
            return {
                "success": False,
                "message": "No scrape is currently running"
            }

        logger.info("Stop requested for running scrape")
        scrape_status.is_running = False  # This will cause the scraping loop to exit

        return {
            "success": True,
            "message": "Scrape stop requested"
        }
    except Exception as e:
        logger.error(f"Error stopping scrape: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/ai-info")
async def get_ai_info_endpoint():
    """
    GET /api/admin/ai-info
    Returns the current AI provider and model information.
    """
    try:
        return {
            "success": True,
            "data": {
                "provider": config.ai_provider,
                "base_url": config.ai_base_url,
                "model": config.ai_model,
                "embedding_model": config.embedding_model,
                "embedding_device": config.embedding_device
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/ai-test")
async def test_ai_connection(request: AITestRequest):
    """
    POST /api/admin/ai-test
    Tests the AI connection with the provided or configured credentials.
    """
    try:
        # Use provided credentials or fall back to configured ones
        provider = request.provider
        base_url = request.base_url or config.ai_base_url
        api_key = request.api_key or config.ai_api_key
        model = request.model or config.ai_model
        
        # Create a temporary client for testing
        test_client = ZhipuAIClient(
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        
        # Try to get a simple response
        result = test_client.chat(request.test_message)
        
        if result.get("success"):
            return {
                "success": True,
                "message": "AI connection test successful",
                "data": {
                    "provider": provider,
                    "base_url": base_url,
                    "model": model,
                    "response": result.get("response", ""),
                    "usage": result.get("usage", {})
                }
            }
        else:
            return {
                "success": False,
                "message": "AI connection test failed",
                "error": result.get("error", "Unknown error")
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Admin Database Management Endpoints ==============

@app.get("/api/admin/db-stats")
async def get_db_stats():
    """
    GET /api/admin/db-stats
    Returns database statistics from Milvus.
    """
    global milvus_store
    try:
        if milvus_store is None:
            initialize_milvus_components()
            if milvus_store is None:
                raise HTTPException(status_code=503, detail="Milvus store not available")

        # Get stats from Milvus store
        stats = milvus_store.health_check()

        # Get additional Milvus-specific stats
        collection_info = milvus_store.get_collection_info()

        # Get document registry stats (single instantiation for efficiency)
        from src.document_registry import DocumentRegistry
        registry = DocumentRegistry()
        indexed_files = registry.get_indexed_files()

        # Get last indexed time
        last_indexed = "N/A"
        if indexed_files:
            most_recent = None
            for file_path, file_info in indexed_files.items():
                indexed_at = file_info.get('indexed_at', '')
                if indexed_at:
                    if most_recent is None or indexed_at > most_recent:
                        most_recent = indexed_at
            if most_recent:
                try:
                    from src.date_utils import format_iso_datetime_short
                    last_indexed = format_iso_datetime_short(most_recent)
                except Exception:
                    last_indexed = most_recent[:16]

        # Calculate document count (reuse indexed_files)
        document_count = len(indexed_files) if indexed_files else 0

        return {
            "status": "ok",
            # Core metrics
            "chunks": stats.get("count", 0),
            "documents": document_count,
            "unique_sources": stats.get("unique_sources", 0),
            # Milvus-specific info
            "index_type": collection_info.get("index_type", "HNSW"),
            "embedding_dim": collection_info.get("embedding_dim", 1024),
            "metric_type": collection_info.get("metric_type", "COSINE"),
            # Connection info
            "connection": f"{stats.get('host', config.milvus_host)}:{stats.get('port', config.milvus_port)}",
            "collection": config.milvus_collection,
            "health": "healthy" if stats.get("healthy") else "unhealthy",
            # Last indexed
            "last_indexed": last_indexed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/performance-metrics")
async def get_performance_metrics():
    """
    GET /api/admin/performance-metrics
    Returns performance metrics from the global performance monitor.
    """
    global performance_monitor

    try:
        metrics = performance_monitor.get_metrics()
        query_times = metrics.get("query_times", [])

        summary = {
            "total_queries": len(query_times),
            "avg_response_time_ms": performance_monitor.get_average_time(),
            "p50_ms": performance_monitor.get_percentile(50),
            "p95_ms": performance_monitor.get_percentile(95),
            "p99_ms": performance_monitor.get_percentile(99),
        }

        by_language = {}
        for lang, data in metrics.get("by_language", {}).items():
            by_language[lang] = {
                "count": data["count"],
                "avg_ms": round(data["total_ms"] / data["count"], 2) if data["count"] > 0 else 0,
                "total_ms": round(data["total_ms"], 2)
            }

        by_path = {}
        for path, data in metrics.get("by_path", {}).items():
            by_path[path] = {
                "count": data["count"],
                "avg_ms": round(data["total_ms"] / data["count"], 2) if data["count"] > 0 else 0,
                "total_ms": round(data["total_ms"], 2)
            }

        return {
            "status": "ok",
            "summary": summary,
            "by_language": by_language,
            "by_path": by_path,
            "stages": metrics.get("stages", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/verify-index")
async def verify_index_endpoint():
    """
    GET /api/admin/verify-index
    Verify index integrity and return detailed statistics.

    Returns:
        Index verification results including counts, sources, and any errors
    """
    try:
        result = verify_index()
        return {
            "success": result.get("success", True),
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/health-check")
async def health_check_endpoint():
    """
    GET /api/admin/health-check
    Performs a comprehensive health check on the Milvus RAG system.

    Returns:
        Health status of Milvus, embedding model, and LLM.
    """
    global milvus_store, llm_client

    health_status = {
        "healthy": True,
        "checks": {}
    }

    # Check Milvus
    try:
        if milvus_store is None:
            initialize_milvus_components()
            if milvus_store is None:
                health_status["checks"]["milvus"] = {"healthy": False, "error": "Not initialized"}
                health_status["healthy"] = False
            else:
                milvus_health = milvus_store.health_check()
                health_status["checks"]["milvus"] = {
                    "healthy": milvus_health.get("healthy", False),
                    "collection": config.milvus_collection,
                    "count": milvus_health.get("count", 0)
                }
                if not milvus_health.get("healthy", False):
                    health_status["healthy"] = False
        else:
            milvus_health = milvus_store.health_check()
            health_status["checks"]["milvus"] = {
                "healthy": milvus_health.get("healthy", False),
                "collection": config.milvus_collection,
                "count": milvus_health.get("count", 0)
            }
            if not milvus_health.get("healthy", False):
                health_status["healthy"] = False
    except Exception as e:
        health_status["checks"]["milvus"] = {"healthy": False, "error": str(e)}
        health_status["healthy"] = False

    # Check LLM
    try:
        if llm_client is None:
            llm_client = ZhipuAIClient(
                api_key=config.ai_api_key,
                base_url=config.ai_base_url,
                model=config.ai_model,
                timeout=30,
            )

        # Test with a simple call
        test_result = llm_client.chat(prompt="test")
        llm_healthy = test_result.get("success", False)

        health_status["checks"]["llm"] = {
            "healthy": llm_healthy,
            "provider": config.ai_provider,
            "model": config.ai_model
        }
        if not llm_healthy:
            health_status["healthy"] = False
    except Exception as e:
        health_status["checks"]["llm"] = {"healthy": False, "error": str(e)}
        health_status["healthy"] = False

    # Check embedding model
    health_status["checks"]["embedding"] = {
        "healthy": True,
        "model": "BAAI/bge-m3",
        "dimensions": 1024
    }

    return {
        "status": "ok",
        "data": health_status
    }


@app.post("/api/admin/migrate")
async def migrate_database():
    """
    POST /api/admin/migrate
    Runs database migration (rebuilds the Milvus index from source documents).

    This is a FULL REBUILD - all previous index data is cleared
    and recreated from source files in data/input directory.
    """
    global milvus_store, milvus_rag
    try:
        # Get old count
        old_count = 0
        try:
            if milvus_store is None:
                initialize_milvus_components()
            if milvus_store:
                old_stats = milvus_store.health_check()
                old_count = old_stats.get("count", 0)
        except Exception:
            pass

        # Rebuild Milvus index
        result = rebuild_index_full()

        # Reinitialize Milvus store and RAG to use new index
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )
        milvus_rag = None  # Force reinitialize on next query

        new_count = result.get("chunks_indexed", 0)

        return {
            "success": result.get("success", True),
            "message": result.get("message", "Milvus index migration completed."),
            "operation": result.get("operation", "rebuild"),
            "oldChunks": old_count,
            "newChunks": new_count,
            "filesProcessed": result.get("files_processed", 0),
            "chunksIndexed": new_count,
            "processingTimeSeconds": result.get("processing_time_seconds", 0),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/upload-data")
async def upload_data():
    """
    POST /api/admin/upload-data
    Uploads/processes data from the documents directory.

    This auto-detects and indexes only NEW documents (incremental update).
    For a full rebuild, use /api/admin/migrate instead.
    """
    global milvus_store
    try:
        # Get current count
        old_count = 0
        try:
            if milvus_store is None:
                initialize_milvus_components()
            if milvus_store:
                old_stats = milvus_store.health_check()
                old_count = old_stats.get("count", 0)
        except Exception:
            pass

        # Index new files using Milvus
        result = index_new_files_only()

        # Get new count
        new_count = result.get("chunks_indexed", 0) + old_count

        return {
            "success": result.get("success", True),
            "message": result.get("message", "Data uploaded successfully."),
            "operation": result.get("operation", "add"),
            "chunksBefore": old_count,
            "chunksAfter": new_count,
            "chunksAdded": result.get("chunks_indexed", 0),
            "filesProcessed": result.get("files_processed", 0),
            "chunksIndexed": result.get("chunks_indexed", 0),
            "processingTimeSeconds": result.get("processing_time_seconds", 0),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    POST /api/admin/upload-pdf
    Upload a PDF file to the scraped/pdfs directory.

    The PDF file will be saved and can be processed by the indexer.
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed"
            )

        # Create pdfs directory if it doesn't exist
        pdfs_dir = Path("./data/input/scraped/pdfs")
        pdfs_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        filename = file.filename
        # Replace spaces and special characters with underscores
        filename = filename.replace(' ', '_').replace("'", '_')
        filename = "".join(c if c.isalnum() or c in '._-' else '_' for c in filename)

        file_path = pdfs_dir / filename

        # Check if file already exists
        if file_path.exists():
            return {
                "success": False,
                "message": f"File {filename} already exists",
                "error": "File already exists"
            }

        # Save the file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        file_size = len(content)

        return {
            "success": True,
            "message": f"PDF file {filename} uploaded successfully",
            "filename": filename,
            "size": file_size,
            "path": str(file_path)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload PDF: {str(e)}"
        )


@app.post("/api/admin/deduplicate")
async def deduplicate_data():
    """
    POST /api/admin/deduplicate
    Removes duplicate entries from the Milvus database.

    Note: Milvus uses document registry to prevent duplicate inserts.
    This endpoint rebuilds the index to ensure no duplicates exist.
    """
    global milvus_store, milvus_rag
    try:
        # Get count before deduplication
        old_count = 0
        try:
            if milvus_store is None:
                initialize_milvus_components()
            if milvus_store:
                old_stats = milvus_store.health_check()
                old_count = old_stats.get("count", 0)
        except Exception:
            pass

        # Rebuild index (effectively deduplicates)
        result = rebuild_index_full()

        # Reinitialize Milvus store and RAG
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )
        milvus_rag = None

        new_count = result.get("chunks_indexed", 0)

        return {
            "success": True,
            "message": "Deduplication completed via index rebuild.",
            "chunksBefore": old_count,
            "chunksAfter": new_count,
            "duplicatesRemoved": old_count - new_count if new_count < old_count else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Incremental Indexing Endpoints ==============

@app.post("/api/admin/index-files")
async def index_uploaded_files(request: IndexFilesRequest):
    """
    POST /api/admin/index-files
    Incrementally index specific uploaded files.

    Body:
        {"files": ["path/to/file1.pdf", "path/to/file2.txt", ...]}

    Returns indexing progress and results.
    """
    try:
        # Run indexing in background thread to avoid blocking
        def run_indexing():
            try:
                return index_files(request.files)
            except Exception as e:
                return {"success": False, "error": str(e)}

        # For now, run synchronously (can be made async later)
        result = index_files(request.files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/index-new")
async def index_new_files():
    """
    POST /api/admin/index-new
    Automatically find and index only new (unindexed) files using Milvus.

    This is useful for:
    - After crawler downloads new content
    - After uploading new PDF or text files
    - Manual trigger to index any pending files

    Returns number of files and chunks indexed.
    """
    global milvus_indexer
    try:
        # Initialize Milvus indexer if not already initialized
        if milvus_indexer is None:
            initialize_milvus_components()

        # Index new files using Milvus
        result = index_new_files_only()

        return {
            "success": result.get("success", True),
            "message": result.get("message", "Indexing completed"),
            "files_processed": result.get("files_processed", 0),
            "chunks_indexed": result.get("chunks_indexed", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/index-progress")
async def get_index_progress():
    """
    GET /api/admin/index-progress
    Get the current indexing progress.

    Returns status, file being processed, chunks completed, etc.
    """
    return index_progress.to_dict()


@app.post("/api/admin/index-reset")
async def reset_index_progress():
    """
    POST /api/admin/index-reset
    Reset the indexing progress tracker.
    """
    index_progress.reset()
    return {"success": True, "message": "Index progress reset"}


# ============== Document Upload Endpoints ==============

class DocumentUploadResponse(BaseModel):
    """文档上传响应模型。"""
    success: bool
    message: str
    file_name: str
    file_path: str
    chunks_added: int = 0
    was_duplicate: bool = False
    file_size: int = 0


class DocumentStatsResponse(BaseModel):
    """文档统计响应模型。"""
    total_files: int
    total_chunks: int
    last_indexed: Optional[str]
    milvus_chunk_count: int
    registry_path: str
    collection_name: str
    healthy: bool


@app.post("/api/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    POST /api/documents/upload

    上传并索引文档到 Milvus 向量数据库。

    支持的文件格式:
    - .txt - 纯文本文件
    - .pdf - PDF 文档
    - .md - Markdown 文档

    流程:
    1. 验证文件类型和大小
    2. 检查是否为重复文档（使用 DocumentRegistry）
    3. 保存文件到 data/input/uploaded/ 目录
    4. 使用 MilvusIndexer 生成文档块和嵌入
    5. 插入向量到 Milvus 数据库
    6. 更新文档注册表

    Args:
        file: 上传的文件

    Returns:
        DocumentUploadResponse: 包含上传状态和索引信息
    """
    global milvus_store, milvus_indexer, document_registry

    # 初始化组件（如果尚未初始化）
    if milvus_indexer is None or document_registry is None:
        initialize_milvus_components()

    if milvus_indexer is None or document_registry is None:
        raise HTTPException(
            status_code=503,
            detail="Milvus 组件未初始化，请检查 Milvus 服务是否运行"
        )

    # 验证文件类型
    file_extension = Path(file.filename).suffix.lower()
    allowed_extensions = {".txt", ".pdf", ".md"}

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file_extension}。支持的类型: {', '.join(allowed_extensions)}"
        )

    # 获取上传目录
    upload_dir = get_upload_dir()

    # 生成唯一文件名（保留原始扩展名）
    unique_id = str(uuid.uuid4())[:8]
    original_name = Path(file.filename).stem
    safe_name = f"{unique_id}_{original_name}{file_extension}"
    file_path = upload_dir / safe_name

    # 保存上传的文件
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_size = file_path.stat().st_size
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")

    # 检查是否为重复文档
    file_path_str = str(file_path.resolve())
    is_duplicate = document_registry.is_indexed(file_path_str)

    chunks_added = 0

    if not is_duplicate:
        # 处理并索引文档
        try:
            # 根据文件类型确定处理方式
            file_type = "pdf" if file_extension == ".pdf" else "text"

            # 分块文档
            chunks = milvus_indexer._chunk_document(file_path, file_type)

            if not chunks:
                # 删除空文件
                file_path.unlink()
                raise HTTPException(
                    status_code=400,
                    detail="文档内容为空或无法解析"
                )

            # 生成嵌入
            texts = [chunk.text for chunk in chunks]
            import numpy as np
            embeddings = milvus_indexer.embedding_model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            # 插入到 Milvus
            chunks_added = milvus_indexer._insert_chunks(chunks, embeddings)

            # 标记为已索引
            document_registry.mark_indexed(
                file_path_str,
                metadata={
                    "file_name": file.filename,
                    "original_name": original_name,
                    "file_size": str(file_size),
                    "uploaded_at": datetime.now().isoformat(),
                    "chunks_count": str(chunks_added),
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            # 索引失败时删除文件
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=500,
                detail=f"索引文档失败: {str(e)}"
            )
    else:
        # 重复文件，删除上传的文件
        file_path.unlink()

    return DocumentUploadResponse(
        success=True,
        message="文档上传成功" if not is_duplicate else "文档已存在（重复）",
        file_name=file.filename,
        file_path=str(file_path),
        chunks_added=chunks_added,
        was_duplicate=is_duplicate,
        file_size=file_size,
    )


@app.get("/api/documents/stats", response_model=DocumentStatsResponse)
async def get_document_stats():
    """
    GET /api/documents/stats

    获取文档统计信息。

    返回:
    - 已索引文件总数（来自 DocumentRegistry）
    - 文档块总数（来自 DocumentRegistry 和 Milvus）
    - 最后索引时间
    - Milvus 集合健康状态

    Returns:
        DocumentStatsResponse: 文档统计信息
    """
    global milvus_store, document_registry

    # 初始化组件（如果尚未初始化）
    if document_registry is None:
        initialize_milvus_components()

    if document_registry is None:
        raise HTTPException(
            status_code=503,
            detail="DocumentRegistry 未初始化"
        )

    # 获取注册表统计
    registry_stats = document_registry.get_stats()

    # 获取 Milvus 统计
    milvus_chunk_count = 0
    collection_name = "documents"
    healthy = False

    if milvus_store is not None:
        try:
            milvus_stats = milvus_store.get_stats()
            milvus_chunk_count = milvus_stats.get("chunk_count", 0)
            collection_name = milvus_stats.get("collection_name", "documents")
            healthy = milvus_stats.get("healthy", False)
        except Exception as e:
            logging.warning(f"获取 Milvus 统计失败: {e}")

    return DocumentStatsResponse(
        total_files=registry_stats["total_files"],
        total_chunks=registry_stats["total_chunks"],
        last_indexed=registry_stats["last_indexed"],
        milvus_chunk_count=milvus_chunk_count,
        registry_path=registry_stats["registry_path"],
        collection_name=collection_name,
        healthy=healthy,
    )


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8086"))

    print(f"🚀 Starting Chatbot API Server on port {port}...")
    print(f"📝 API docs available at http://localhost:{port}/docs")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
