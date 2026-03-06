#!/usr/bin/env python3
"""Entry point script to run backend CLI from project root."""
import sys
import os
from pathlib import Path

# Get the backend directory and change to it
backend_dir = Path(__file__).parent / "backend"
os.chdir(str(backend_dir))
sys.path.insert(0, str(backend_dir))

# Import and run the CLI
from src.cli import main

if __name__ == "__main__":
    main()
