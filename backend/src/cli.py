"""CLI interface for the chatbot."""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown

from .config import config
from .document import DocumentProcessor
from .embedding import EmbeddingClient
from .zhipuai_llm import ZhipuAIClient

# Milvus 相关导入
from .milvus_store import MilvusStore
from .milvus_indexer import MilvusIndexer
from .milvus_rag import MilvusRAGPipeline, detect_language, LANGUAGE_NAMES
from .translation_service import FreeTranslationService

app = typer.Typer(help="Multilingual Document Chatbot CLI")
console = Console()


def print_banner():
    """Print welcome banner."""
    console.print(
        Panel.fit(
            "[bold blue]Multilingual Document Chatbot[/bold blue]\n"
            "[dim]Powered by RAG + GitHub Copilot[/dim]",
            border_style="blue",
        )
    )


@app.command()
def index(
    input_dir: str = typer.Option(
        None, "--input", "-i", help="Input directory with PDF and text files"
    ),
    clear: bool = typer.Option(
        False, "--clear", "-c", help="Clear existing index before indexing"
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Process subdirectories recursively"
    ),
    verbose: bool = typer.Option(
        True, "--verbose", "-v", help="Show detailed progress"
    ),
):
    """Index PDF and text documents into Milvus vector database."""
    print_banner()

    # Use config default if not specified
    if input_dir is None:
        input_dir = config.documents_path

    console.print("\n[bold cyan]Using Milvus vector database for semantic search[/bold cyan]\n")

    # Initialize Milvus indexer
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing Milvus...", total=None)

        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=clear,  # Clear if requested
        )

        progress.update(task, description="Milvus initialized!")

        # Create indexer
        indexer = MilvusIndexer(
            milvus_store,
            embedding_model="BAAI/bge-m3",
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

        # Rebuild index
        if clear:
            console.print("[yellow]Rebuilding Milvus index...[/yellow]")
        else:
            console.print("[yellow]Adding new documents to Milvus index...[/yellow]")

        input_path = Path(input_dir).resolve()
        if not input_path.exists():
            console.print(f"[red]Error: Directory not found: {input_path}[/red]")
            raise typer.Exit(1)

        # Run indexing
        progress.update(task, description="Indexing documents...")
        chunk_count = indexer.rebuild(str(input_path))

        console.print(f"\n[green]✅ Indexing complete![/green]")
        console.print(f"   Total chunks indexed: [bold]{chunk_count}[/bold]")
        console.print(f"   Collection: [bold]{config.milvus_collection}[/bold]")
        console.print(f"   Embedding model: [bold]BAAI/bge-m3[/bold]")
        console.print(f"   Semantic search: [bold green]Enabled (HNSW + COSINE)[/bold green]")

    raise typer.Exit(0)


@app.command()
def query(
    question: Optional[str] = typer.Option(
        None, "--question", "-q", help="Question to ask"
    ),
    lang: str = typer.Option(
        "auto", "--lang", "-l", help="Target language: zh, en, fr, auto"
    ),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to retrieve"),
    verbose: bool = typer.Option(
        True, "--verbose", "-v", help="Show detailed retrieval info"
    ),
):
    """Query the knowledge base using Milvus."""
    print_banner()

    # Check if index exists
    try:
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
        )
        health = milvus_store.health_check()
        indexed_count = health.get("count", 0)
    except Exception as e:
        console.print(
            f"[red]Error: Cannot connect to Milvus: {e}[/red]"
        )
        raise typer.Exit(1)

    if indexed_count == 0:
        console.print(
            "[red]Error: No documents indexed. Run 'index' command first.[/red]"
        )
        raise typer.Exit(1)

    console.print(f"📚 Knowledge base: [bold]{indexed_count}[/bold] chunks indexed\n")

    # Use ZhipuAI with config from .env
    llm_client = ZhipuAIClient(
        api_key=config.ai_api_key,
        base_url=config.ai_base_url,
        model=config.ai_model,
        timeout=60,
    )

    # Test API with a simple call (more reliable than SDK health_check)
    try:
        test_result = llm_client.chat(prompt="test")
        if not test_result.get("success"):
            console.print(f"[red]Error: LLM API returned: {test_result.get('error', 'Unknown error')}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: Cannot connect to LLM API: {e}[/red]")
        console.print("[yellow]Check your API key and internet connection[/yellow]")
        raise typer.Exit(1)

    # Interactive mode if no question provided
    if question is None:
        console.print("[dim]Type 'quit' or 'exit' to exit[/dim]\n")
        interactive_query(lang, top_k, verbose)
    else:
        run_single_query(question, lang, top_k, verbose)


def interactive_query(lang: str, top_k: int, verbose: bool):
    """Interactive query loop using Milvus RAG."""
    # Initialize Milvus RAG
    milvus_store = MilvusStore(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=config.milvus_collection,
    )

    embedding_client = EmbeddingClient(
        model_name="BAAI/bge-m3",
        device=config.embedding_device,
    )

    llm_client = ZhipuAIClient()

    translation_service = FreeTranslationService(llm_client=llm_client)

    milvus_rag = MilvusRAGPipeline(
        milvus_store=milvus_store,
        embedding_client=embedding_client,
        llm_client=llm_client,
        translation_service=translation_service,
        top_k=top_k,
    )

    while True:
        try:
            question = console.input("\n[bold cyan]Q:[/bold cyan] ")

            if question.lower() in ["quit", "exit", "q"]:
                console.print("[dim]Goodbye![/dim]")
                break

            if not question.strip():
                continue

            # Run query
            result = milvus_rag.query(question)

            # Display results
            console.print("\n[bold cyan]━━━ Milvus Semantic Search ━━━[/bold cyan]")

            # Show answer
            console.print("\n[bold]━━━ Answer ━━━[/bold]")

            detected_lang = LANGUAGE_NAMES.get(
                result["metadata"]["language"], result["metadata"]["language"]
            )
            console.print(f"[dim]Query language: {detected_lang}[/dim]")

            if result["metadata"].get("translated"):
                console.print(f"[dim]Query was translated for search[/dim]")

            console.print()
            console.print(Panel(result["answer"], border_style="cyan"))

            # Show sources
            if result.get("sources"):
                console.print("\n[bold]📚 Sources:[/bold]")
                for source in result["sources"][:5]:
                    console.print(
                        f"  • {source['source']} (score: {source['score']:.2f})"
                    )

            # Show timing
            metadata = result["metadata"]
            console.print(
                f"\n[dim]⏱️  Search time: {metadata.get('search_time_ms', 0):.0f}ms | "
                f"Generation time: {metadata.get('generation_time_ms', 0):.0f}ms | "
                f"Total: {metadata.get('total_time_ms', 0):.0f}ms[/dim]"
            )

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break


def run_single_query(question: str, lang: str, top_k: int, verbose: bool):
    """Run a single query using Milvus RAG."""
    # Import MilvusRAG
    from .milvus_rag import MilvusRAGPipeline

    # Initialize Milvus RAG
    milvus_store = MilvusStore(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=config.milvus_collection,
    )

    embedding_client = EmbeddingClient(
        model_name="BAAI/bge-m3",
        device=config.embedding_device,
    )

    llm_client = ZhipuAIClient()

    from .translation_service import FreeTranslationService
    translation_service = FreeTranslationService(llm_client=llm_client)

    milvus_rag = MilvusRAGPipeline(
        milvus_store=milvus_store,
        embedding_client=embedding_client,
        llm_client=llm_client,
        translation_service=translation_service,
        top_k=top_k,
    )

    # Run query
    result = milvus_rag.query(question)

    # Display results
    console.print("\n[bold cyan]━━━ Milvus Semantic Search ━━━[/bold cyan]")

    # Show answer
    console.print("\n[bold]━━━ Answer ━━━[/bold]")

    detected_lang = LANGUAGE_NAMES.get(
        result["metadata"]["language"], result["metadata"]["language"]
    )
    console.print(f"[dim]Query language: {detected_lang}[/dim]")

    if result["metadata"].get("translated"):
        console.print(f"[dim]Query was translated for search[/dim]")

    console.print()
    console.print(Panel(result["answer"], border_style="cyan"))

    # Show sources
    if result.get("sources"):
        console.print("\n[bold]📚 Sources:[/bold]")
        for source in result["sources"][:5]:
            console.print(
                f"  • {source['source']} (score: {source['score']:.2f})"
            )

    # Show timing
    metadata = result["metadata"]
    console.print(
        f"\n[dim]⏱️  Search time: {metadata.get('search_time_ms', 0):.0f}ms | "
        f"Generation time: {metadata.get('generation_time_ms', 0):.0f}ms | "
        f"Total: {metadata.get('total_time_ms', 0):.0f}ms[/dim]"
    )



@app.command()
def info():
    """Show Milvus index information and statistics."""
    print_banner()

    console.print("\n[bold cyan]📊 Milvus Index Statistics[/bold cyan]\n")

    # Initialize Milvus store
    milvus_store = MilvusStore(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=config.milvus_collection,
    )

    # Get collection info
    stats = milvus_store.health_check()

    table = Table(show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Vector Database", "[bold cyan]Milvus[/bold cyan]")
    table.add_row("Collection", config.milvus_collection)
    table.add_row("Host", f"{config.milvus_host}:{config.milvus_port}")
    table.add_row("Embedding Model", "[bold]BAAI/bge-m3[/bold] (1024 dim)")
    table.add_row("Index Type", "[bold green]HNSW[/bold green] (Semantic Search)")
    table.add_row("Metric Type", "[bold green]COSINE[/bold green] (Similarity)")
    table.add_row("Total Chunks", str(stats.get("count", "N/A")))
    table.add_row("LLM Provider", config.ai_provider)
    table.add_row("LLM Model", config.ai_model)
    table.add_row("API Base URL", config.ai_base_url)

    console.print(table)

    # Check ZhipuAI status
    llm_client = ZhipuAIClient(
        api_key=config.ai_api_key,
        base_url=config.ai_base_url,
        model=config.ai_model,
        timeout=30,
    )

    # Test with actual API call instead of health_check
    test_result = llm_client.chat(prompt="test")
    if test_result.get("success"):
        console.print(f"\n[green]✅ {config.ai_provider} {config.ai_model}: Connected[/green]")
    else:
        console.print(f"\n[red]❌ {config.ai_provider} {config.ai_model}: Not connected[/red]")
        console.print(f"[yellow]  Error: {test_result.get('error', 'Unknown')}[/yellow]")


@app.command()
def clear(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Clear all indexed documents from Milvus."""
    print_banner()

    if not force:
        confirm = typer.confirm("Are you sure you want to clear the Milvus index?")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    console.print("[yellow]Clearing Milvus index...[/yellow]")

    # Reset Milvus collection
    milvus_store = MilvusStore(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=config.milvus_collection,
        reset=True,  # This clears the collection
    )

    console.print("[green]✅ Milvus index cleared[/green]")
    console.print("[dim]Use 'python -m src.cli index' to rebuild the index[/dim]")


@app.command("rebuild-milvus")
def rebuild_milvus(
    input_dir: str = typer.Option(
        None, "--input", "-i", help="Input directory with PDF and text files"
    ),
    reset: bool = typer.Option(
        False, "--reset", "-r", help="Reset Milvus collection before rebuilding"
    ),
):
    """从源文档重建 Milvus 索引。"""
    print_banner()

    # 使用配置默认值
    if input_dir is None:
        input_dir = config.documents_path

    input_path = Path(input_dir).resolve()

    if not input_path.exists():
        console.print(f"[red]Error: Directory not found: {input_path}[/red]")
        raise typer.Exit(1)

    console.print(f"\n📁 Input directory: [bold]{input_path}[/bold]\n")

    # 创建 Milvus 存储
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting to Milvus...", total=None)

        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=reset,
        )

        progress.update(task, description="Milvus connected!")

    # 创建索引构建器
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing indexer...", total=None)

        progress.update(task, description="Indexer ready!")

    # 重建索引
    indexer = MilvusIndexer(
        milvus_store=milvus_store,
        embedding_model="BAAI/bge-m3",
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    count = indexer.rebuild(input_dir=str(input_path))

    # 显示结果
    console.print(f"\n[green]✅ Index rebuilt with [bold]{count}[/bold] chunks[/green]")

    health = milvus_store.health_check()
    console.print(f"📊 Total chunks in Milvus: [bold]{health.get('count', 0)}[/bold]")
    console.print(f"📦 Collection: [bold]{config.milvus_collection}[/bold]")
    console.print(f"🔢 Embedding model: [bold]BAAI/bge-m3[/bold]")


@app.command("add-documents")
def add_documents(
    input_dir: str = typer.Option(
        None, "--input", "-i", help="Input directory with PDF and text files"
    ),
):
    """增量添加新文档到 Milvus 索引。"""

    # 使用配置默认值
    if input_dir is None:
        input_dir = config.documents_path

    input_path = Path(input_dir).resolve()

    if not input_path.exists():
        console.print(f"[red]Error: Directory not found: {input_path}[/red]")
        raise typer.Exit(1)

    console.print(f"\n📁 Input directory: [bold]{input_path}[/bold]\n")

    # 创建 Milvus 存储
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting to Milvus...", total=None)

        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )

        progress.update(task, description="Milvus connected!")

    # 创建索引构建器
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing indexer...", total=None)

        indexer = MilvusIndexer(
            milvus_store=milvus_store,
            embedding_model="BAAI/bge-m3",
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

        progress.update(task, description="Indexer ready!")

    # 增量添加文档
    stats = indexer.add_new_documents(input_dir=str(input_path))

    # 显示结果
    console.print(f"\n[green]✅ Added [bold]{stats.get('added', 0)}[/bold] documents[/green]")
    console.print(f"📊 Chunks added: [bold]{stats.get('chunks_added', 0)}[/bold]")
    console.print(f"⏭️ Skipped: [bold]{stats.get('skipped', 0)}[/bold] existing documents")

    # 显示 Milvus 统计
    health = milvus_store.health_check()
    console.print(f"📈 Total in Milvus: [bold]{health.get('count', 0)}[/bold]")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
