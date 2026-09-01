#!/usr/bin/env python3
"""Report frequent words and phrases in daily arXiv titles and abstracts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import snowballstemmer

from arxiv_client import (
    discover_daily_ids,
    fetch_metadata,
    load_metadata_cache,
    save_metadata_cache,
)


CATEGORIES = {
    "q-fin": "Quantitative Finance",
    "stat": "Statistics",
    "cs.AI": "Artificial Intelligence",
}
DEFAULT_CACHE = Path(".cache/arxiv-withcode/metadata.json")
TOKEN_PATTERN = re.compile(r"[a-z]+(?:'[a-z]+)?")
SENTENCE_PATTERN = re.compile(r"[.!?;:\n]+")

# Function words plus terms that describe papers rather than their subject matter.
STOP_WORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because
    been before being below between both but by can cannot could couldn't did didn't
    do does doesn't doing don't down during each few for from further had hadn't has
    hasn't have haven't having he her here hers herself him himself his how i if in
    into is isn't it its itself just may me might more most must my myself no nor not
    of off on once only or other ought our ours ourselves out over own same shall she
    should shouldn't so some such than that the their theirs them themselves then
    there these they this those through to too under until up very was wasn't we were
    weren't what when where which while who whom why will with won't would wouldn't
    you your yours yourself yourselves also approach based demonstrate introduce
    investigate method methods new paper papers present presents propose proposed
    result results show shows shown study studies use used uses using work works
    across among first framework however one second three throughout two via within
    """.split()
)


def tokenize(text: str) -> list[str]:
    normalized = text.lower().replace("-", " ").replace("’", "'")
    return [token.removesuffix("'s") for token in TOKEN_PATTERN.findall(normalized)]


def significant_runs(text: str) -> Iterable[list[str]]:
    for sentence in SENTENCE_PATTERN.split(text):
        run: list[str] = []
        for token in tokenize(sentence):
            if len(token) < 2 or token in STOP_WORDS:
                if run:
                    yield run
                    run = []
            else:
                run.append(token)
        if run:
            yield run


def _rank_counts(
    total_counts: Counter[object],
    document_counts: Counter[object],
    surfaces: dict[object, Counter[str]],
    limit: int,
) -> list[dict[str, object]]:
    rows = []
    for key, occurrences in total_counts.items():
        variants = surfaces[key]
        display = sorted(variants, key=lambda item: (-variants[item], len(item), item))[0]
        rows.append(
            {
                "term": display,
                "occurrences": occurrences,
                "papers": document_counts[key],
            }
        )
    rows.sort(key=lambda row: (-row["occurrences"], -row["papers"], row["term"]))
    return rows[:limit]


def analyze_documents(documents: list[str], *, limit: int = 10) -> dict[str, object]:
    stemmer = snowballstemmer.stemmer("english")
    word_totals: Counter[str] = Counter()
    word_documents: Counter[str] = Counter()
    word_surfaces: dict[str, Counter[str]] = {}
    phrase_totals: Counter[tuple[str, ...]] = Counter()
    phrase_documents: Counter[tuple[str, ...]] = Counter()
    phrase_surfaces: dict[tuple[str, ...], Counter[str]] = {}

    for document in documents:
        document_words: Counter[str] = Counter()
        document_phrases: Counter[tuple[str, ...]] = Counter()
        for run in significant_runs(document):
            stems = stemmer.stemWords(run)
            for token, stem in zip(run, stems):
                document_words[stem] += 1
                word_surfaces.setdefault(stem, Counter())[token] += 1
            for size in (2, 3):
                for start in range(len(run) - size + 1):
                    key = tuple(stems[start:start + size])
                    surface = " ".join(run[start:start + size])
                    document_phrases[key] += 1
                    phrase_surfaces.setdefault(key, Counter())[surface] += 1

        word_totals.update(document_words)
        word_documents.update(document_words.keys())
        phrase_totals.update(document_phrases)
        phrase_documents.update(document_phrases.keys())

    return {
        "paper_count": len(documents),
        "top_words": _rank_counts(
            word_totals, word_documents, word_surfaces, limit
        ),
        "top_phrases": _rank_counts(
            phrase_totals, phrase_documents, phrase_surfaces, limit
        ),
    }


def build_report(
    target_date: str,
    ids_by_category: dict[str, list[str]],
    metadata: dict[str, dict[str, object]],
    *,
    limit: int = 10,
) -> dict[str, object]:
    sections: dict[str, dict[str, object]] = {}
    for category, arxiv_ids in ids_by_category.items():
        available_ids = [
            arxiv_id
            for arxiv_id in arxiv_ids
            if metadata.get(arxiv_id, {}).get("title")
            or metadata.get(arxiv_id, {}).get("abstract")
        ]
        documents = [
            f"{metadata[arxiv_id].get('title', '')}. "
            f"{metadata[arxiv_id].get('abstract', '')}"
            for arxiv_id in available_ids
        ]
        analysis = analyze_documents(documents, limit=limit)
        analysis.update(
            {
                "name": CATEGORIES.get(category, category),
                "listed_papers": len(arxiv_ids),
                "missing_metadata": sorted(set(arxiv_ids) - set(available_ids)),
            }
        )
        sections[category] = analysis

    combined_ids = sorted({arxiv_id for ids in ids_by_category.values() for arxiv_id in ids})
    combined_available = [
        arxiv_id
        for arxiv_id in combined_ids
        if metadata.get(arxiv_id, {}).get("title")
        or metadata.get(arxiv_id, {}).get("abstract")
    ]
    combined_documents = [
        f"{metadata[arxiv_id].get('title', '')}. "
        f"{metadata[arxiv_id].get('abstract', '')}"
        for arxiv_id in combined_available
    ]
    combined = analyze_documents(combined_documents, limit=limit)
    combined.update(
        {
            "name": "Combined (deduplicated)",
            "listed_papers": len(combined_ids),
            "missing_metadata": sorted(set(combined_ids) - set(combined_available)),
        }
    )
    return {
        "date": target_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "source": "arXiv daily listings and Atom API metadata",
            "fields": ["title", "abstract"],
            "normalization": "lowercase, English stop words, Snowball stemming",
            "phrases": "contiguous 2-3 word sequences without stop words",
            "ranking": "occurrences, then paper frequency, then alphabetical",
        },
        "categories": sections,
        "combined": combined,
    }


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        f"# Daily arXiv Keywords: {report['date']}",
        "",
        "Source: titles and abstracts from arXiv metadata. The combined section "
        "deduplicates papers listed in multiple archives.",
        "",
    ]
    sections = list(report["categories"].values()) + [report["combined"]]
    for section in sections:
        lines.extend(
            [
                f"## {section['name']}",
                "",
                f"Listed papers: {section['listed_papers']} | "
                f"Analyzed papers: {section['paper_count']} | "
                f"Missing metadata: {len(section['missing_metadata'])}",
                "",
                "### Top Words",
                "",
                "| Rank | Word | Occurrences | Papers |",
                "|---:|---|---:|---:|",
            ]
        )
        for rank, row in enumerate(section["top_words"], 1):
            lines.append(
                f"| {rank} | {row['term']} | {row['occurrences']} | {row['papers']} |"
            )
        lines.extend(
            [
                "",
                "### Top Phrases",
                "",
                "| Rank | Phrase | Occurrences | Papers |",
                "|---:|---|---:|---:|",
            ]
        )
        for rank, row in enumerate(section["top_phrases"], 1):
            lines.append(
                f"| {rank} | {row['term']} | {row['occurrences']} | {row['papers']} |"
            )
        lines.append("")
    return "\n".join(lines)


def parse_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count frequent words and phrases in daily q-fin, stat, and cs.AI metadata."
    )
    parser.add_argument("--date", type=parse_date, default=date.today().isoformat())
    parser.add_argument("--top", type=int, default=10, help="number of results per table")
    parser.add_argument("--output-dir", type=Path, default=Path("keyword_reports"))
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    if args.top < 1:
        parser.error("--top must be at least 1")

    ids_by_category = {
        category: discover_daily_ids(category, args.date) for category in CATEGORIES
    }
    for category, arxiv_ids in ids_by_category.items():
        print(f"{category}: found {len(arxiv_ids)} papers for {args.date}")
    if not any(ids_by_category.values()):
        parser.error(
            f"no q-fin, stat, or cs.AI listing entries found for {args.date}; "
            "check the date or arXiv announcement schedule"
        )
    cache = load_metadata_cache(args.cache)
    all_ids = sorted({arxiv_id for ids in ids_by_category.values() for arxiv_id in ids})
    missing_ids = [
        arxiv_id
        for arxiv_id in all_ids
        if not cache.get(arxiv_id, {}).get("title")
        and not cache.get(arxiv_id, {}).get("abstract")
    ]
    if missing_ids:
        cache.update(fetch_metadata(missing_ids))
        save_metadata_cache(args.cache, cache)

    report = build_report(args.date, ids_by_category, cache, limit=args.top)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"daily_keywords_{args.date}"
    json_path = args.output_dir / f"{stem}.json"
    markdown_path = args.output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Analyzed {report['combined']['paper_count']} unique papers.")
    print(f"Markdown: {markdown_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
