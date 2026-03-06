#!/usr/bin/env python3
"""
Enhanced scraper that downloads all pages and PDFs from school website.
"""
import sys
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Set
import requests
from bs4 import BeautifulSoup

# Configuration
BASE_URL = "https://collegesaintlouis.ecolelachine.com"
SCRAPED_DIR = Path("data/input/scraped")
TIMEOUT = 30

# Browser-like headers to avoid 403 Forbidden errors
SCRAPER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def fetch_html(url: str) -> str:
    """Fetch HTML from URL."""
    try:
        response = requests.get(url, headers=SCRAPER_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  ❌ Error fetching {url}: {e}")
        return ""


def extract_info_parents_pdf_urls(html: str, base_url: str) -> List[str]:
    """Extract PDF URLs from Info-parents category page."""
    soup = BeautifulSoup(html, 'html.parser')
    pdf_urls = []

    # Find all Info-parents articles
    for article in soup.find_all('article'):
        # Get the link to the individual Info-parents page
        link_tag = article.find('a', href=True)
        if link_tag and 'info-parents' in link_tag.get('href', '').lower():
            individual_url = urljoin(base_url, link_tag['href'])

            # Fetch the individual page to get the PDF download link
            individual_html = fetch_html(individual_url)
            if individual_html:
                individual_soup = BeautifulSoup(individual_html, 'html.parser')

                # Find PDF download link
                for a in individual_soup.find_all('a', href=True):
                    href = a.get('href', '')
                    # Look for PDF links
                    if '.pdf' in href.lower() or (a.text and 'pdf' in a.text.lower()):
                        pdf_url = urljoin(individual_url, href)
                        pdf_urls.append(pdf_url)
                        break

    return pdf_urls


def extract_all_pdf_urls_from_site(base_url: str) -> List[str]:
    """Extract all PDF URLs from the site."""
    all_pdfs = []

    # Pages that likely contain PDFs
    pdf_pages = [
        f"{base_url}/category/info-parents/",
        f"{base_url}/le-college/admission/",
        f"{base_url}/vie-pedagogique/programmes-detudes/",
    ]

    for page_url in pdf_pages:
        print(f"  Scanning for PDFs: {page_url}")
        html = fetch_html(page_url)
        if html:
            soup = BeautifulSoup(html, 'html.parser')

            # Find all PDF links
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                if '.pdf' in href or '/documents/' in href:
                    full_url = urljoin(page_url, a['href'])
                    all_pdfs.append(full_url)
                    print(f"    Found: {a.text[:50]}")

    return list(set(all_pdfs))


def download_pdf(url: str, output_dir: Path, index: int) -> bool:
    """Download a PDF file."""
    try:
        response = requests.get(url, headers=SCRAPER_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        # Try to get filename from Content-Disposition header
        filename = None
        if 'content-disposition' in response.headers:
            import re
            cd = response.headers['content-disposition']
            filenames = re.findall('filename=(?:"([^"]+)"|([^;]+))', cd)
            if filenames:
                filename = filenames[0].strip('"')
                filename = filename.encode('latin-1').decode('utf-8', errors='ignore')

        # If no filename in headers, get from URL
        if not filename:
            # Try to extract filename from URL path
            parsed = urlparse(url)
            path_parts = parsed.path.split('/')
            if path_parts:
                filename = path_parts[-1]
                if not filename.endswith('.pdf'):
                    filename = f"document_{index}.pdf"
            else:
                filename = f"document_{index}.pdf"

        # Clean filename
        filename = re.sub(r'[^\w\-_\.]', '_', filename)

        # Save PDF
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / filename

        with open(pdf_path, 'wb') as f:
            f.write(response.content)

        print(f"  ✅ Downloaded: {filename}")
        return True

    except Exception as e:
        print(f"  ❌ Error downloading PDF {url}: {e}")
        return False


def main():
    """Main function."""
    print("=" * 80)
    print("ENHANCED WEBSITE SCRAPER")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Output directory: {SCRAPED_DIR}")
    print()

    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract all PDF URLs
    print("Step 1: Extracting PDF URLs from site...")
    print("-" * 40)
    pdf_urls = extract_all_pdf_urls_from_site(BASE_URL)
    print(f"Found {len(pdf_urls)} PDF URLs")
    print()

    # Step 2: Download all PDFs
    print("Step 2: Downloading PDFs...")
    print("-" * 40)

    documents_dir = SCRAPED_DIR / "pdfs"
    documents_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for i, pdf_url in enumerate(pdf_urls, 1):
        print(f"[{i}/{len(pdf_urls)}] {pdf_url}")
        if download_pdf(pdf_url, documents_dir, i):
            downloaded += 1
        time.sleep(0.5)

    print()
    print("=" * 80)
    print(f"SCRAPING COMPLETE!")
    print(f"PDFs downloaded: {downloaded}/{len(pdf_urls)}")
    print(f"PDFs saved to: {documents_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
