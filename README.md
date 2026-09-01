```
# first
uv sync

# daily (workday)
uv run python main.py
```

```
# optional
uv run python main.py --download-only
uv run python main.py --search-only 
```

## Daily q-fin, Statistics, and AI Keywords

Count the most frequent words and two-to-three-word phrases in titles and
abstracts published in the `q-fin`, `stat`, and `cs.AI` archives. This
metadata-only workflow does not download PDFs.

```bash
uv run python daily_keywords.py
uv run python daily_keywords.py --date 2026-08-31
```

The command writes Markdown and JSON reports to `keyword_reports/`, with
separate results for Quantitative Finance, Statistics, Artificial
Intelligence, and a deduplicated combined corpus. Each result includes both
total occurrences and paper frequency.


https://github.com/arXiv/arxiv-pdftotext
https://github.com/lukasschwab/arxiv.py
https://github.com/arxiv
