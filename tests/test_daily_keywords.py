import unittest

from daily_keywords import analyze_documents, build_report, render_markdown


class KeywordAnalysisTests(unittest.TestCase):
    def test_groups_inflections_and_counts_document_frequency(self):
        result = analyze_documents(
            [
                "Risk models model market risk. Time-series models.",
                "Market risks and a time series model.",
            ]
        )

        words = {row["term"]: row for row in result["top_words"]}
        self.assertEqual(words["model"]["occurrences"], 4)
        self.assertEqual(words["model"]["papers"], 2)
        self.assertEqual(words["risk"]["occurrences"], 3)
        self.assertEqual(words["risk"]["papers"], 2)

        phrases = {row["term"]: row for row in result["top_phrases"]}
        self.assertEqual(phrases["time series"]["occurrences"], 2)
        self.assertEqual(phrases["time series"]["papers"], 2)

    def test_stop_words_break_phrases(self):
        result = analyze_documents(["risk of market data"], limit=20)
        phrases = {row["term"] for row in result["top_phrases"]}
        self.assertNotIn("risk market", phrases)
        self.assertIn("market data", phrases)


class ReportTests(unittest.TestCase):
    def test_combined_report_deduplicates_cross_listed_papers(self):
        metadata = {
            "2609.00001": {"title": "Market risk", "abstract": "Risk model"},
            "2609.00002": {"title": "Bayesian data", "abstract": "Data model"},
        }
        report = build_report(
            "2026-09-01",
            {
                "q-fin": ["2609.00001"],
                "stat": ["2609.00001", "2609.00002"],
                "cs.AI": ["2609.00002"],
            },
            metadata,
        )

        self.assertEqual(report["combined"]["listed_papers"], 2)
        self.assertEqual(report["combined"]["paper_count"], 2)
        markdown = render_markdown(report)
        self.assertIn("## Quantitative Finance", markdown)
        self.assertIn("## Artificial Intelligence", markdown)
        self.assertIn("## Combined (deduplicated)", markdown)


if __name__ == "__main__":
    unittest.main()
