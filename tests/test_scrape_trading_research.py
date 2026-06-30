import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scrapling.engines.toolbelt.custom import Response
from scrapling.spiders.result import CrawlStats, ItemList

from scripts import scrape_trading_research as script


def response(html: str, *, url: str = "https://arxiv.org/search/") -> Response:
    return Response(
        url=url,
        content=html,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


class TradingResearchScraperTests(unittest.TestCase):
    def test_fixed_source_filters_unrelated_publications(self) -> None:
        page = response(
            """
            <article><h3><a href="https://arxiv.org/abs/1234">Momentum trading strategy</a></h3></article>
            <article><h3><a href="https://arxiv.org/abs/5678">Marine biology survey</a></h3></article>
            """,
            url="https://oxford-man.ox.ac.uk/selected-publications/",
        )

        records = script.parse_source_response(
            page,
            spec=script.SOURCES["oxford_man"],
            query="momentum trading",
            collected_at="2026-06-30T00:00:00+00:00",
            limit=10,
        )

        self.assertEqual([record.title for record in records], ["Momentum trading strategy"])

    def test_nber_json_parser_keeps_working_papers(self) -> None:
        page = response(
            json.dumps(
                {
                    "results": [
                        {"type": "entity:user", "title": "A person", "url": "/people/person"},
                        {
                            "type": "working_paper",
                            "title": "Machine Learning in Currency Markets",
                            "url": "/papers/w123",
                            "authors": ['<a href="/people/a">Ada Quant</a>'],
                            "displaydate": "June 2025",
                            "abstract": "A cost-aware study.",
                        },
                    ]
                }
            ),
            url="https://www.nber.org/api/v1/search?q=currency",
        )

        records = script.parse_source_response(
            page,
            spec=script.SOURCES["nber"],
            query="currency",
            collected_at="2026-06-30T00:00:00+00:00",
            limit=10,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].authors, "Ada Quant")
        self.assertEqual(records[0].year, 2025)
        self.assertEqual(records[0].url, "https://www.nber.org/papers/w123")

    def test_openalex_parser_retains_repository_location(self) -> None:
        page = response(
            json.dumps(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "doi": None,
                            "display_name": "Forex Forecasting",
                            "publication_year": 2024,
                            "publication_date": "2024-02-01",
                            "authorships": [{"author": {"display_name": "A. Trader"}}],
                            "abstract_inverted_index": {"Trading": [0], "costs": [1]},
                            "locations": [
                                {
                                    "landing_page_url": "https://arxiv.org/abs/2401.1",
                                    "pdf_url": "https://arxiv.org/pdf/2401.1",
                                    "source": {"id": "https://openalex.org/S4306400194"},
                                }
                            ],
                        }
                    ]
                }
            ),
            url="https://api.openalex.org/works",
        )

        records = script.parse_source_response(
            page,
            spec=script.SOURCES["arxiv"],
            query="forex",
            collected_at="2026-06-30T00:00:00+00:00",
            limit=10,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].abstract, "Trading costs")
        self.assertEqual(records[0].url, "https://arxiv.org/abs/2401.1")

    def test_openalex_researchgate_parser_requires_researchgate_location(self) -> None:
        page = response(
            json.dumps(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W2",
                            "display_name": "Cost-Aware Trading",
                            "publication_year": 2023,
                            "publication_date": "2023-04-01",
                            "authorships": [],
                            "locations": [
                                {
                                    "landing_page_url": (
                                        "https://www.researchgate.net/publication/123_Cost-Aware_Trading"
                                    ),
                                    "pdf_url": None,
                                    "source": None,
                                }
                            ],
                        },
                        {
                            "id": "https://openalex.org/W3",
                            "display_name": "Unrelated repository copy",
                            "publication_year": 2023,
                            "publication_date": "2023-04-02",
                            "authorships": [],
                            "locations": [
                                {
                                    "landing_page_url": "https://example.org/paper",
                                    "pdf_url": None,
                                    "source": None,
                                }
                            ],
                        },
                    ]
                }
            ),
            url="https://api.openalex.org/works",
        )

        records = script.parse_source_response(
            page,
            spec=script.SOURCES["researchgate"],
            query="trading",
            collected_at="2026-06-30T00:00:00+00:00",
            limit=10,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "researchgate")
        self.assertIn("researchgate.net", records[0].url)

    def test_spider_uses_native_polite_crawl_controls(self) -> None:
        spider = script.TradingResearchSpider(
            source_names=("arxiv", "nber"),
            query="trading",
            collected_at="2026-06-30T00:00:00+00:00",
            max_results_per_source=10,
            timeout_seconds=5,
            delay_seconds=1.5,
            concurrent_requests=3,
            max_blocked_retries=1,
        )

        self.assertTrue(spider.robots_txt_obey)
        self.assertEqual(spider.concurrent_requests, 3)
        self.assertEqual(spider.concurrent_requests_per_domain, 1)
        self.assertEqual(spider.download_delay, 1.5)
        self.assertEqual(spider.max_blocked_retries, 1)
        self.assertEqual(spider.allowed_domains, {"api.openalex.org", "www.nber.org"})

    def test_main_writes_outputs_and_native_crawl_stats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            fake_result = SimpleNamespace(
                items=ItemList(),
                stats=CrawlStats(
                    requests_count=2,
                    robots_disallowed_count=1,
                    start_time=1.0,
                    end_time=2.0,
                ),
                paused=False,
                completed=True,
            )
            with (
                patch.object(script.TradingResearchSpider, "start", return_value=fake_result),
                patch("builtins.print"),
            ):
                code = script.main(
                    [
                        "--sources",
                        "arxiv",
                        "--output-dir",
                        str(output),
                        "--name",
                        "fixture",
                    ]
                )

            manifest = json.loads((output / "fixture_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(manifest["record_count"], 0)
            self.assertEqual(manifest["sources"][0]["status"], "not_fetched")
            self.assertEqual(manifest["crawl"]["stats"]["robots_disallowed_count"], 1)
            self.assertTrue((output / "fixture.csv").exists())
            self.assertTrue((output / "fixture.jsonl").exists())

    def test_deduplication_prefers_first_canonical_url(self) -> None:
        record = script.PaperRecord(
            record_id="one",
            title="A strategy",
            authors="",
            abstract="",
            published="",
            year=None,
            url="https://example.test/paper/1",
            pdf_url="",
            doi="",
            source="one",
            query="trading",
            collected_at="now",
        )
        duplicate = script.PaperRecord(**{**record.__dict__, "record_id": "two", "source": "two"})

        self.assertEqual(script.deduplicate_records([record, duplicate]), [record])


if __name__ == "__main__":
    unittest.main()
