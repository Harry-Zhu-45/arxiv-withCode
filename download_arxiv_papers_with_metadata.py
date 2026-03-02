#!/usr/bin/env python3
"""
ArXiv Paper Downloader + Metadata Fetcher

Downloads PDFs for a category/date and fetches title/abstract via arXiv API.
This is a standalone test script; it does not modify main.py behavior.

Usage:
    uv run python download_arxiv_papers_with_metadata.py 2026-03-02 -c quant-ph
    uv run python download_arxiv_papers_with_metadata.py today -c physics.optics
"""

import argparse
import re
import sys
import time
import urllib.request
import urllib.error
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class ArxivPaper:
    """ArXiv paper record with metadata."""
    def __init__(self, arxiv_id: str, title: str, date: str):
        self.arxiv_id = arxiv_id
        self.title = title
        self.date = date
        self.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        self.abstract = ""

    def __repr__(self):
        return f"ArxivPaper(id={self.arxiv_id})"


def parse_arxiv_page(html_content: str, target_date: str) -> List[ArxivPaper]:
    """Parse arXiv listing HTML and extract papers for the target date."""
    papers: List[ArxivPaper] = []

    month_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
    }

    date_header_pattern = r"<h3>\s*([A-Z][a-z]{2},\s+(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4}))"
    date_positions = []
    for match in re.finditer(date_header_pattern, html_content):
        day = match.group(2)
        month_abbrev = match.group(3)
        year = match.group(4)
        month = month_map.get(month_abbrev, "01")
        parsed_date = f"{year}-{month}-{day.zfill(2)}"
        date_positions.append({"date": parsed_date, "start": match.end()})

    if date_positions:
        date_positions.append({"date": None, "start": len(html_content)})

    for i, dp in enumerate(date_positions[:-1]):
        if dp["date"] != target_date:
            continue

        start_pos = dp["start"]
        end_pos = date_positions[i + 1]["start"]
        date_block = html_content[start_pos:end_pos]

        title_pattern = r"<div class='list-title[^>]*>.*?<span class='descriptor'>Title:</span>\s*(.+?)</div>"
        titles = re.findall(title_pattern, date_block, re.DOTALL)

        pdf_pattern = r"/pdf/(\d{4}\.\d{4,5})"
        pdfs = re.findall(pdf_pattern, date_block)

        for j, arxiv_id in enumerate(pdfs):
            title = titles[j] if j < len(titles) else f"Paper {arxiv_id}"
            title = re.sub(r"\s+", " ", title).strip()
            papers.append(ArxivPaper(arxiv_id, title, dp["date"]))

    return papers


def fetch_url(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch URL content as text with basic retry handling."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    for attempt in range(3):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

        if attempt < 2:
            time.sleep(2 ** attempt)

    return None


def fetch_arxiv_metadata(arxiv_ids: List[str]) -> Dict[str, Dict[str, str]]:
    """Fetch title/abstract for a list of arXiv IDs via the official API."""
    if not arxiv_ids:
        return {}

    # API allows comma-separated ids; keep batches small and safe.
    base_url = "http://export.arxiv.org/api/query?id_list="
    batch_size = 50
    metadata: Dict[str, Dict[str, str]] = {}

    for i in range(0, len(arxiv_ids), batch_size):
        batch = arxiv_ids[i:i + batch_size]
        url = base_url + ",".join(batch)
        xml_text = fetch_url(url, timeout=40)
        if not xml_text:
            continue

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"API parse error: {e}", file=sys.stderr)
            continue

        ns = {
            "atom": "http://www.w3.org/2005/Atom",
        }

        for entry in root.findall("atom:entry", ns):
            id_node = entry.find("atom:id", ns)
            title_node = entry.find("atom:title", ns)
            summary_node = entry.find("atom:summary", ns)

            if id_node is None:
                continue

            # ID format: http://arxiv.org/abs/1234.5678v1
            abs_url = id_node.text.strip() if id_node.text else ""
            arxiv_id = abs_url.rsplit("/", 1)[-1].split("v", 1)[0]

            title = title_node.text.strip() if title_node is not None and title_node.text else ""
            summary = summary_node.text.strip() if summary_node is not None and summary_node.text else ""

            # Normalize whitespace
            title = re.sub(r"\s+", " ", title)
            summary = re.sub(r"\s+", " ", summary)

            metadata[arxiv_id] = {
                "title": title,
                "abstract": summary,
            }

        time.sleep(0.5)

    return metadata


def download_pdf(url: str, output_path: str) -> bool:
    """Download a PDF file."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    for attempt in range(3):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
                content = response.read()
                with open(output_path, "wb") as f:
                    f.write(content)
                return True
        except Exception as e:
            print(f"  Download failed (attempt {attempt + 1}/3): {e}", file=sys.stderr)
            if attempt < 2:
                time.sleep(2 ** attempt)

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Download arXiv PDFs and fetch metadata via API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "date",
        nargs="?",
        default="yesterday",
        help="Date (YYYY-MM-DD) or 'yesterday'/'today'",
    )
    parser.add_argument(
        "--date",
        "-d",
        dest="date_alt",
        help="Date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./arxiv_papers",
        help="Output directory (default: ./arxiv_papers)",
    )
    parser.add_argument(
        "--category",
        "-c",
        default="quant-ph",
        help="ArXiv category (default: quant-ph)",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Only fetch metadata without downloading PDFs",
    )

    args = parser.parse_args()
    date_str = args.date_alt if args.date_alt else args.date

    if date_str.lower() == "today":
        target_date = datetime.now().strftime("%Y-%m-%d")
    elif date_str.lower() == "yesterday":
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            target_date = date_str
        except ValueError:
            print("Error: invalid date format, use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)

    print(f"Target date: {target_date}")
    print(f"Category: {args.category}")
    print(f"Output dir: {args.output}")
    print("-" * 50)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_dir = output_dir / f"arxiv_{args.category}_{target_date}"
    date_dir.mkdir(parents=True, exist_ok=True)

    base_url = f"https://arxiv.org/list/{args.category}/recent"
    all_papers: List[ArxivPaper] = []

    print("Fetching listing pages...")
    page = 0
    while page < 5:
        url = base_url if page == 0 else f"{base_url}?skip={page * 50}&show=50"
        print(f"  Page {page + 1}: {url}")
        html_content = fetch_url(url)
        if not html_content:
            print(f"  Failed to fetch page {page + 1}")
            break

        papers = parse_arxiv_page(html_content, target_date)
        if not papers:
            print(f"  No papers found for target date on page {page + 1}")
            break

        all_papers.extend(papers)
        if len(papers) < 50:
            break

        page += 1
        time.sleep(1)

    if not all_papers:
        print("No papers found.")
        sys.exit(0)

    print(f"Found {len(all_papers)} papers. Fetching metadata...")
    id_list = [p.arxiv_id for p in all_papers]
    metadata = fetch_arxiv_metadata(id_list)

    for p in all_papers:
        meta = metadata.get(p.arxiv_id)
        if meta:
            p.title = meta.get("title", p.title)
            p.abstract = meta.get("abstract", "")

    print("-" * 50)

    if args.metadata_only:
        for p in all_papers[:5]:
            abstract_preview = (p.abstract[:200] + "...") if len(p.abstract) > 200 else p.abstract
            print(f"{p.arxiv_id}: {p.title}")
            print(f"  Abstract: {abstract_preview}")
        print("Metadata fetched only. No PDFs downloaded.")
        return

    print("Downloading PDFs...")
    success_count = 0
    fail_count = 0

    for i, paper in enumerate(all_papers, 1):
        output_file = date_dir / f"{paper.arxiv_id}.pdf"
        title_short = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
        print(f"[{i}/{len(all_papers)}] {paper.arxiv_id}.pdf - {title_short}")

        if output_file.exists():
            print("    Exists, skipped")
            success_count += 1
            continue

        if download_pdf(paper.pdf_url, str(output_file)):
            print("    Done")
            success_count += 1
        else:
            print("    Failed")
            fail_count += 1

        time.sleep(0.3)

    print("-" * 50)
    print("Download finished")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Output: {date_dir}")


if __name__ == "__main__":
    main()
