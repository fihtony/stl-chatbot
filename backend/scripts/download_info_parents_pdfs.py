#!/usr/bin/env python3
"""
Download Info-parents PDFs from the school website using curl to avoid 403 errors.
"""
import sys
import re
import subprocess
import time
from pathlib import Path
from typing import List
import requests

# Configuration
BASE_URL = "https://collegesaintlouis.ecolelachine.com"
SCRAPED_DIR = Path("data/input/scraped")
TIMEOUT = 30


# Browser headers to avoid 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def get_pdf_urls() -> List[str]:
    """Get all Info-parents PDF URLs."""
    pdf_urls = []

    # Info-parents months to check
    months = [
        "fevrier-2026", "janvier-2026", "decembre-2025",
        "novembre-2025", "octobre-2025", "septembre-2025"
    ]

    for month in months:
        page_url = f"{BASE_URL}/info-parents-{month}/"
        print(f"Checking: {page_url}")

        try:
            response = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()

            # Extract PDF URL from page
            pattern = r'https://collegesaintlouis\.ecolelachine\.com/wp-content/uploads/\d{4}/\d{2}/Info-parents-[^"]+\.pdf'
            matches = re.findall(pattern, response.text)

            if matches:
                pdf_url = matches[0]
                print(f"  Found PDF: {pdf_url}")
                pdf_urls.append(pdf_url)
            else:
                print(f"  No PDF found")

            time.sleep(0.5)

        except Exception as e:
            print(f"  Error: {e}")

    # Add additional URLs from user
    additional_urls = [
        "https://collegesaintlouis.ecolelachine.com/wp-content/uploads/2025/05/InfoParentsCSL_Mai2025.pdf",
        "https://collegesaintlouis.ecolelachine.com/wp-content/uploads/2025/03/Info-parents-de-mars-2025.pdf",
    ]

    for url in additional_urls:
        if url not in pdf_urls:
            pdf_urls.append(url)
            print(f"  Added: {url}")

    return pdf_urls


def download_pdf_curl(url: str, output_dir: Path) -> bool:
    """Download a PDF file using curl to avoid 403 errors."""
    try:
        # Extract filename from URL
        filename = url.split('/')[-1]
        filename = re.sub(r'%20', '_', filename)

        # Save PDF
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / filename

        # Use curl with browser headers
        headers_str = " ".join([f'-H "{k}: {v}"' for k, v in HEADERS.items()])

        cmd = f'curl -s {headers_str} -o "{pdf_path}" "{url}"'

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 1000:
            size = pdf_path.stat().st_size
            print(f"  ✅ Downloaded: {filename} ({size:,} bytes)")
            return True
        else:
            print(f"  ❌ Failed: {filename}")
            return False

    except Exception as e:
        print(f"  ❌ Error downloading {url}: {e}")
        return False


def main():
    """Main function."""
    print("=" * 80)
    print("DOWNLOADING INFO-PARENTS PDFS (using curl)")
    print("=" * 80)
    print()

    # Get PDF URLs
    print("Step 1: Finding PDF URLs...")
    print("-" * 40)
    pdf_urls = get_pdf_urls()
    print(f"\nFound {len(pdf_urls)} PDF URLs")
    print()

    # Download PDFs
    print("Step 2: Downloading PDFs...")
    print("-" * 40)

    pdfs_dir = SCRAPED_DIR / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    for pdf_url in pdf_urls:
        if download_pdf_curl(pdf_url, pdfs_dir):
            downloaded += 1
        else:
            failed += 1
        time.sleep(0.5)

    print()
    print("=" * 80)
    print(f"DOWNLOAD COMPLETE!")
    print(f"PDFs downloaded: {downloaded}/{len(pdf_urls)}")
    print(f"PDFs failed: {failed}")
    print(f"PDFs saved to: {pdfs_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
