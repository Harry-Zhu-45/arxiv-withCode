"""Small arXiv client for daily listings and paper metadata."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


USER_AGENT = "arxiv-withCode/0.1 (daily metadata analysis)"
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


def normalize_whitespace(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize_arxiv_id(value: object) -> str:
    normalized = normalize_whitespace(value).rsplit("/", 1)[-1]
    normalized = normalized.removesuffix(".pdf").split("?", 1)[0]
    return re.sub(r"v\d+$", "", normalized)


def fetch_text(url: str, *, timeout: int = 40, max_retries: int = 3) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/html"},
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to fetch {url}: {error}") from error
            time.sleep(2**attempt)
    raise AssertionError("retry loop ended unexpectedly")


def parse_daily_listing(page: str, target_date: str) -> list[str]:
    """Return unique paper IDs under a date heading on an arXiv list page."""
    month_numbers = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
    }
    heading_pattern = re.compile(
        r"<h3[^>]*>\s*[A-Z][a-z]{2},\s+(\d{1,2})\s+"
        r"([A-Z][a-z]{2})\s+(\d{4})[^<]*</h3>",
        re.IGNORECASE,
    )
    headings = list(heading_pattern.finditer(page))
    paper_ids: list[str] = []
    seen: set[str] = set()

    for index, heading in enumerate(headings):
        day, month_name, year = heading.groups()
        listing_date = f"{year}-{month_numbers.get(month_name.title(), '00')}-{int(day):02d}"
        if listing_date != target_date:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(page)
        block = html.unescape(page[heading.end():end])
        for match in re.finditer(r"href\s*=\s*[\"']/abs/([^\"'?#]+)", block):
            arxiv_id = normalize_arxiv_id(match.group(1))
            if arxiv_id and arxiv_id not in seen:
                seen.add(arxiv_id)
                paper_ids.append(arxiv_id)

    return paper_ids


def discover_daily_ids(category: str, target_date: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", category):
        raise ValueError(f"Invalid arXiv category: {category}")
    url = f"https://arxiv.org/list/{category}/recent?skip=0&show=2000"
    return parse_daily_listing(fetch_text(url), target_date)


def parse_atom_feed(xml_text: str) -> dict[str, dict[str, object]]:
    root = ET.fromstring(xml_text)
    metadata: dict[str, dict[str, object]] = {}
    for entry in root.findall("atom:entry", ATOM_NAMESPACE):
        id_node = entry.find("atom:id", ATOM_NAMESPACE)
        if id_node is None or not id_node.text:
            continue
        arxiv_id = normalize_arxiv_id(id_node.text)
        title_node = entry.find("atom:title", ATOM_NAMESPACE)
        summary_node = entry.find("atom:summary", ATOM_NAMESPACE)
        authors = [
            normalize_whitespace(node.text)
            for node in entry.findall("atom:author/atom:name", ATOM_NAMESPACE)
            if normalize_whitespace(node.text)
        ]
        metadata[arxiv_id] = {
            "title": normalize_whitespace(title_node.text if title_node is not None else ""),
            "abstract": normalize_whitespace(
                summary_node.text if summary_node is not None else ""
            ),
            "authors": authors,
        }
    return metadata


def fetch_metadata(arxiv_ids: list[str], *, batch_size: int = 50) -> dict[str, dict[str, object]]:
    normalized_ids = list(dict.fromkeys(filter(None, map(normalize_arxiv_id, arxiv_ids))))
    metadata: dict[str, dict[str, object]] = {}
    for start in range(0, len(normalized_ids), batch_size):
        batch = normalized_ids[start:start + batch_size]
        query = urllib.parse.urlencode(
            {"id_list": ",".join(batch), "start": 0, "max_results": len(batch)}
        )
        metadata.update(parse_atom_feed(fetch_text(f"https://export.arxiv.org/api/query?{query}")))
        if start + batch_size < len(normalized_ids):
            time.sleep(0.5)
    return metadata


def load_metadata_cache(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_metadata_cache(path: Path, metadata: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
