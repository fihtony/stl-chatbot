#!/usr/bin/env python3
"""
ScrapeConfig class with JSON persistence.
Manages persistent crawler configuration.
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any

# Use absolute path to backend data directory
BACKEND_DIR = Path(__file__).parent.parent
CONFIG_FILE = BACKEND_DIR / "data" / "scrape_config.json"


class ScrapeConfig:
    """Persistent scrape configuration manager."""

    DEFAULTS = {
        "school_url": "https://collegesaintlouis.ecolelachine.com",
        "schedule_enabled": False,
        "schedule_time": "02:00",
        "output_dir": "./data/input/scraped",
        "timeout": 30,
        "respect_robots_txt": True,
        "max_pages": None,  # No limit - crawl all pages
        "max_pdfs": None,   # No limit - download all PDFs
        "seed_urls": [],
    }

    # Type hints for class attributes
    school_url: str
    schedule_enabled: bool
    schedule_time: str
    output_dir: str
    timeout: int
    respect_robots_txt: bool
    max_pages: int
    max_pdfs: int
    seed_urls: list

    def __init__(self, **kwargs):
        for key, value in self.DEFAULTS.items():
            setattr(self, key, kwargs.get(key, value))

    @classmethod
    def load(cls) -> "ScrapeConfig":
        """Load from JSON file, fallback to defaults."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError):
                logging.warning("Failed to parse config file, using defaults")
        else:
            logging.info("Config file not found, using defaults")
        return cls()

    def save(self) -> bool:
        """Save to JSON file."""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logging.error(f"Failed to save config: {e}")
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "school_url": self.school_url,
            "schedule_enabled": self.schedule_enabled,
            "schedule_time": self.schedule_time,
            "output_dir": self.output_dir,
            "timeout": self.timeout,
            "respect_robots_txt": self.respect_robots_txt,
            "max_pages": getattr(self, "max_pages", None),
            "max_pdfs": getattr(self, "max_pdfs", None),
            "seed_urls": getattr(self, "seed_urls", []),
        }

    def to_cron_format(self) -> str:
        """Convert schedule_time (HH:MM) to cron format."""
        hour, minute = self.schedule_time.split(":")
        return f"{minute} {hour} * * *"

    @classmethod
    def load_from_env(cls) -> "ScrapeConfig":
        """Load config from environment variables (legacy support)."""
        cfg = cls()
        cfg.school_url = os.getenv("SCRAPE_SCHOOL_URL", cfg.school_url)
        cfg.schedule_enabled = os.getenv("SCRAPE_SCHEDULE_ENABLED", "false").lower() == "true"
        cron_time = os.getenv("SCRAPE_SCHEDULE_CRON", cfg.to_cron_format())
        # Parse cron "MM HH * * *" to "HH:MM"
        parts = cron_time.split()
        if len(parts) >= 2:
            cfg.schedule_time = f"{parts[1]}:{parts[0]}"
        cfg.output_dir = os.getenv("SCRAPE_OUTPUT_DIR", cfg.output_dir)
        cfg.timeout = int(os.getenv("SCRAPE_TIMEOUT", str(cfg.timeout)))
        cfg.respect_robots_txt = os.getenv("SCRAPE_RESPECT_ROBOTS", "true").lower() == "true"
        return cfg
