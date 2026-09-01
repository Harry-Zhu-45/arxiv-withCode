import unittest

from arxiv_client import parse_atom_feed, parse_daily_listing


class DailyListingTests(unittest.TestCase):
    def test_extracts_target_date_and_deduplicates_versions(self):
        page = """
        <h3>Tue, 1 Sep 2026 (showing 2 entries)</h3>
        <a href ="/abs/2609.00001v1">abs</a>
        <a href='/abs/2609.00001v1'>duplicate</a>
        <a href="/abs/2609.00002">abs</a>
        <h3>Mon, 31 Aug 2026 (showing 1 entry)</h3>
        <a href="/abs/2608.99999">abs</a>
        """

        self.assertEqual(
            parse_daily_listing(page, "2026-09-01"),
            ["2609.00001", "2609.00002"],
        )

    def test_returns_empty_list_when_date_is_absent(self):
        self.assertEqual(parse_daily_listing("<html></html>", "2026-09-01"), [])


class AtomFeedTests(unittest.TestCase):
    def test_parses_and_normalizes_metadata(self):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2609.00001v2</id>
            <title>  A title\n with spaces </title>
            <summary>An abstract. </summary>
            <author><name>Ada Lovelace</name></author>
          </entry>
        </feed>
        """

        self.assertEqual(
            parse_atom_feed(feed),
            {
                "2609.00001": {
                    "title": "A title with spaces",
                    "abstract": "An abstract.",
                    "authors": ["Ada Lovelace"],
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
