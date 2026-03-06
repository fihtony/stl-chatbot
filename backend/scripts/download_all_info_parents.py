#!/usr/bin/env python3
"""
Download ALL Info-parents PDFs from the school website.
Scrapes all pages of the Info-parents category to find all PDFs.
"""
import sys
import re
import subprocess
import time
from pathlib import Path
from typing import List, Set
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


def get_all_info_parents_pages() -> List[str]:
    """Get all Info-parents page URLs by following pagination."""
    all_urls = []
    page_num = 1

    while True:
        # Try both URL patterns
        if page_num == 1:
            url = f"{BASE_URL}/category/info-parents/"
        else:
            url = f"{BASE_URL}/category/info-parents/page/{page_num}/"

        print(f"Checking page {page_num}: {url}")

        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()

            # Check if this is a valid page (not 404)
            if "404 Not Found" in response.text or response.status_code == 404:
                print(f"  Page {page_num} not found, stopping pagination")
                break

            # Check if there are actually info-parents entries on this page
            if 'info-parents' not in response.text.lower():
                print(f"  No info-parents content on page {page_num}, stopping")
                break

            all_urls.append(url)
            print(f"  ✓ Found page {page_num}")

            # Check if there's a next page
            if 'page/' + str(page_num + 1) not in response.text and page_num > 1:
                # Check for "next" link in pagination
                if 'next' not in response.text.lower() or f'page/{page_num + 1}"' not in response.text:
                    print(f"  No more pages found, stopping pagination")
                    break

            page_num += 1
            time.sleep(0.5)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"  Page {page_num} returns 404, stopping pagination")
                break
            print(f"  HTTP error: {e}")
            break
        except Exception as e:
            print(f"  Error: {e}")
            break

    return all_urls


def extract_pdf_urls_from_pages(page_urls: List[str]) -> Set[str]:
    """Extract all PDF URLs from the given pages."""
    pdf_urls = set()

    for page_url in page_urls:
        print(f"Extracting PDFs from: {page_url}")

        try:
            response = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()

            # Find all article links (individual info-parents pages)
            article_links = re.findall(r'https://collegesaintlouis\.ecolelachine\.com/(info-parents-[^/]+/)', response.text)

            print(f"  Found {len(article_links)} article links")

            # Visit each article page to get the PDF download link
            for article_link in article_links:
                article_url = f"{BASE_URL}/{article_link}"
                print(f"    Checking article: {article_url}")

                try:
                    article_response = requests.get(article_url, headers=HEADERS, timeout=TIMEOUT)
                    article_response.raise_for_status()

                    # Find PDF link in the article
                    pdf_matches = re.findall(
                        r'https://collegesaintlouis\.ecolelachine\.com/wp-content/uploads/\d{4}/\d{2}/[^"]+\.pdf',
                        article_response.text
                    )

                    for pdf_url in pdf_matches:
                        pdf_urls.add(pdf_url)
                        print(f"      ✓ Found PDF: {pdf_url.split('/')[-1]}")

                    time.sleep(0.3)

                except Exception as e:
                    print(f"      Error fetching article: {e}")

            time.sleep(0.5)

        except Exception as e:
            print(f"  Error: {e}")

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

        # Check if already exists
        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            print(f"  ✓ Already exists: {filename}")
            return True

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
    print("DOWNLOADING ALL INFO-PARENTS PDFS")
    print("=" * 80)
    print()

    # Step 1: Find all Info-parents pages
    print("Step 1: Finding all Info-parents pages...")
    print("-" * 40)
    page_urls = get_all_info_parents_pages()
    print(f"\nFound {len(page_urls)} Info-parents pages")
    print()

    # Step 2: Extract all PDF URLs
    print("Step 2: Extracting PDF URLs from all pages...")
    print("-" * 40)
    pdf_urls = extract_pdf_urls_from_pages(page_urls)
    print(f"\nFound {len(pdf_urls)} unique PDF URLs")
    print()

    # Print all PDF URLs found
    print("PDF URLs found:")
    for url in sorted(pdf_urls):
        print(f"  - {url.split('/')[-1]}")
    print()

    # Step 3: Download all PDFs
    print("Step 3: Downloading all PDFs...")
    print("-" * 40)

    pdfs_dir = SCRAPED_DIR / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    skipped = 0

    for pdf_url in sorted(pdf_urls):
        result = download_pdf_curl(pdf_url, pdfs_dir)
        if result:
            downloaded += 1
        else:
            failed += 1
        time.sleep(0.5)

    print()
    print("=" * 80)
    print(f"DOWNLOAD COMPLETE!")
    print(f"PDFs downloaded: {downloaded}")
    print(f"PDFs failed: {failed}")
    print(f"PDFs saved to: {pdfs_dir}")
    print("=" * 80)


if __name__ == "__main__":
    from urllib.parse import urljoin
    main()
