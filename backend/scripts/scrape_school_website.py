#!/usr/bin/env python3
"""
Comprehensive web scraper for Collège Saint-Louis website.
Downloads all pages, documents, and PDFs from the school website.
"""
import sys
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Set
import requests
from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class SchoolWebsiteScraper:
    """Scraper for Collège Saint-Louis website."""

    def __init__(self, base_url: str, output_dir: Path):
        self.base_url = base_url
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.visited_urls: Set[str] = set()
        self.download_queue: List[str] = []
        self.pdf_urls: List[str] = []

        # Create subdirectories
        (self.output_dir / "pages").mkdir(exist_ok=True)
        (self.output_dir / "documents").mkdir(exist_ok=True)

    def fetch_page(self, url: str) -> str:
        """Fetch a single page."""
        try:
            response = requests.get(url, headers=SCRAPER_HEADERS, timeout=TIMEOUT)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get('Content-Type', '').lower()

            # Skip binary content
            if any(ct in content_type for ct in ['application/pdf', 'image/', 'video/', 'application/octet-stream']):
                return ""

            # Only process HTML content
            if not any(ct in content_type for ct in ['text/html', 'application/xhtml', 'text/xml']):
                # If no content type header, check the URL and content
                if self.is_pdf_url(url):
                    return ""
                # Check if response looks like HTML
                if not any(tag in response.text[:1000].lower() for tag in ['<html', '<head', '<body', '<doctype']):
                    return ""

            return response.text

        except Exception as e:
            print(f"  ❌ Error fetching {url}: {e}")
            return ""

    def extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all links from HTML."""
        links = []

        # Skip if HTML is empty or doesn't look like HTML
        if not html or len(html) < 50:
            return links
        if '\x00' in html or html.count('\xff') > 10:
            return links
        if not any(tag in html.lower() for tag in ['<html', '<head', '<body', '<div', '<p>', '<a ']):
            return links

        try:
            # Try parsing with different parsers
            soup = None
            for parser in ['html.parser', 'lxml', 'html5lib']:
                try:
                    soup = BeautifulSoup(html, parser)
                    break
                except Exception:
                    continue

            if soup is None:
                return links

            for a in soup.find_all('a', href=True):
                href = a['href']
                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)

                # Only include links from the same domain
                if urlparse(absolute_url).netloc == urlparse(base_url).netloc:
                    # Skip PDF and binary files (they're handled separately)
                    if not self.is_pdf_url(absolute_url) and not any(
                        ext in absolute_url.lower() for ext in [
                            '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
                            '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                            '.zip', '.tar', '.gz', '.mp4', '.mp3', '.mov'
                        ]
                    ):
                        links.append(absolute_url)

        except Exception as e:
            print(f"  ⚠️ Warning: Could not extract links: {e}")

        return links

    def save_page(self, url: str, html: str, page_name: str):
        """Save a page as text file."""
        # Skip if HTML is empty or too short
        if not html or len(html) < 50:
            print(f"  ⚠️ Skipped: {page_name} (empty or invalid content)")
            return

        # Skip if content looks like binary data (PDF, image, etc.)
        # Check for null bytes and non-text characters
        if '\x00' in html or html.count('\xff') > 10:
            print(f"  ⚠️ Skipped: {page_name} (binary data)")
            return

        # Skip if content doesn't look like HTML
        if not any(tag in html.lower() for tag in ['<html', '<head', '<body', '<div', '<p>', '<a ']):
            print(f"  ⚠️ Skipped: {page_name} (not HTML)")
            return

        try:
            # Try parsing with different parsers
            soup = None
            for parser in ['html.parser', 'lxml', 'html5lib']:
                try:
                    soup = BeautifulSoup(html, parser)
                    break  # Success, use this parser
                except Exception:
                    continue

            if soup is None:
                print(f"  ⚠️ Skipped: {page_name} (all parsers failed)")
                return

            # Remove scripts, styles, nav, footer
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            # Get main content
            content = soup.get_text(separator='\n', strip=True)

            # Skip if content is too short
            if len(content) < 20:
                print(f"  ⚠️ Skipped: {page_name} (content too short)")
                return

            # Clean up content
            lines = [line.strip() for line in content.split('\n')]
            lines = [line for line in lines if line]

            # Save as text file
            filename = self.output_dir / "pages" / f"{page_name}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"URL: {url}\n\n")
                f.write(f"{'=' * 80}\n\n")
                f.write('\n'.join(lines))

            print(f"  ✅ Saved: {page_name}.txt")

        except Exception as e:
            print(f"  ⚠️ Skipped: {page_name} (parse error: {e})")
            return

    def is_pdf_url(self, url: str) -> bool:
        """Check if URL points to a PDF file."""
        return any(ext in url.lower() for ext in ['.pdf', '.PDF'])

    def extract_pdf_url(self, html: str, base_url: str) -> List[str]:
        """Extract PDF URLs from HTML."""
        pdf_urls = []

        # Skip if HTML is empty or doesn't look like HTML
        if not html or len(html) < 50:
            return pdf_urls
        if '\x00' in html or html.count('\xff') > 10:
            return pdf_urls
        if not any(tag in html.lower() for tag in ['<html', '<head', '<body', '<div', '<p>', '<a ']):
            return pdf_urls

        try:
            # Try parsing with different parsers
            soup = None
            for parser in ['html.parser', 'lxml', 'html5lib']:
                try:
                    soup = BeautifulSoup(html, parser)
                    break
                except Exception:
                    continue

            if soup is None:
                return pdf_urls

            # Check for direct PDF links
            for a in soup.find_all('a', href=True):
                href = a['href']
                absolute_url = urljoin(base_url, href)

                # Check if it's a PDF
                if self.is_pdf_url(absolute_url):
                    pdf_urls.append(absolute_url)

        except Exception as e:
            print(f"  ⚠️ Warning: Could not extract PDF URLs: {e}")

        return pdf_urls

    def download_pdf(self, url: str) -> bool:
        """Download a PDF file."""
        try:
            response = requests.get(url, headers=SCRAPER_HEADERS, timeout=TIMEOUT)
            response.raise_for_status()

            # Extract filename from URL
            filename = url.split('/')[-1]
            if not filename or len(filename) > 200:
                filename = f"document_{hash(url) % 10000}.pdf"

            # Save PDF
            pdf_path = self.output_dir / "documents" / filename
            with open(pdf_path, 'wb') as f:
                f.write(response.content)

            print(f"  📄 Downloaded PDF: {filename}")
            return True

        except Exception as e:
            print(f"  ❌ Error downloading PDF {url}: {e}")
            return False

    def get_page_name(self, url: str) -> str:
        """Generate a safe filename from URL."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')

        if not path:
            return "homepage"

        # Remove file extension and clean up
        path = re.sub(r'\.\w+$', '', path)  # Remove extension
        path = path.strip('/')

        if not path:
            return "homepage"

        # Convert to safe filename
        path = path.replace('/', '_')
        path = re.sub(r'[^\w\-_]', '_', path)

        # Remove common prefixes
        for prefix in ['le-college', 'la_', 'le_']:
            if path.startswith(prefix):
                path = path[len(prefix):]
                break

        return path[:100]  # Limit length

    def scrape(self):
        """Main scraping method."""
        print("=" * 80)
        print("SCRAPING COLLEGE SAINT-LOUIS WEBSITE")
        print("=" * 80)
        print(f"Base URL: {BASE_URL}")
        print(f"Output directory: {self.output_dir}")
        print()

        # Start with homepage
        self.download_queue.append(BASE_URL)

        total_pages = 0
        total_pdfs = 0

        while self.download_queue:
            url = self.download_queue.pop(0)

            if url in self.visited_urls:
                continue

            self.visited_urls.add(url)

            # Skip certain URLs
            if any(skip in url for skip in ['/wp-json/', '/xmlrpc.php', '/feed/']):
                continue

            # Skip email addresses (invalid URLs)
            if url.startswith('mailto:') or '@' in urlparse(url).path:
                continue

            page_name = self.get_page_name(url)
            print(f"\n📄 Processing: {page_name}")
            print(f"   URL: {url}")

            # Fetch page
            html = self.fetch_page(url)
            if not html:
                continue

            # Save page content
            self.save_page(url, html, page_name)
            total_pages += 1

            # Extract and queue new links
            new_links = self.extract_links(html, url)
            for link in new_links:
                if link not in self.visited_urls and link not in self.download_queue:
                    self.download_queue.append(link)

            # Extract PDF URLs
            pdf_urls = self.extract_pdf_url(html, url)
            for pdf_url in pdf_urls:
                if pdf_url not in self.pdf_urls:
                    self.pdf_urls.append(pdf_url)

            # Small delay to be respectful
            time.sleep(0.5)

        print(f"\n{'=' * 80}")
        print(f"Pages processed: {total_pages}")
        print(f"PDFs found: {len(self.pdf_urls)}")
        print(f"Downloading PDFs...")
        print(f"{'=' * 80}\n")

        # Download all PDFs
        for pdf_url in self.pdf_urls:
            if self.download_pdf(pdf_url):
                total_pdfs += 1

        print(f"\n{'=' * 80}")
        print(f"SCRAPING COMPLETE!")
        print(f"Pages: {total_pages}")
        print(f"PDFs downloaded: {total_pdfs}")
        print(f"{'=' * 80}")

        return total_pages, total_pdfs


def main():
    """Main entry point."""
    scraper = SchoolWebsiteScraper(
        base_url=BASE_URL,
        output_dir=SCRAPED_DIR
    )
    scraper.scrape()


if __name__ == "__main__":
    main()
