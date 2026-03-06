#!/usr/bin/env python3
"""Main entry point for the chatbot CLI."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.cli import main

if __name__ == "__main__":
    main()
