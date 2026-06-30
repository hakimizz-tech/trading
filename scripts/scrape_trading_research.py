#!/usr/bin/env python3
"""Trading Research Paper Metadata Collector.

Script Name:
    scrape_trading_research.py

Description:
    Collect and normalize trading-research paper metadata from public scholarly
    sources. The collector uses Scrapling, obeys robots.txt, applies per-source
    delays, and does not bypass authentication, CAPTCHAs, paywalls, or publisher
    access controls.

Author:
    hakeem <joshuakim408@gmail.com>

Date:
    30 June 2026

Version:
    1.0.0

Usage:
    python scripts/scrape_trading_research.py --help

    python scripts/scrape_trading_research.py \\
        --query "forex machine learning transaction costs" \\
        --sources arxiv repec researchgate nber oxford_man \\
        --name forex_ml_research
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote_plus, urljoin, urlparse

from scrapling.spiders import Request, Response, Spider


USER_AGENT = "TradingResearchCollector/1.0 (+metadata-only; respectful crawler)"
DEFAULT_OUTPUT_DIR = Path("trade_results/research_papers")
SPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


@dataclass(frozen=True)
class SourceSpec:
    """Selectors and URL template for one public research source."""

    name: str
    search_url: str
    item_selectors: tuple[str, ...]
    title_selectors: tuple[str, ...]
    link_selectors: tuple[str, ...]
    author_selectors: tuple[str, ...] = ()
    abstract_selectors: tuple[str, ...] = ()
    date_selectors: tuple[str, ...] = ()
    pdf_selectors: tuple[str, ...] = ()
    fixed_query: bool = False
    parser: str = "html"

    def url_for(self, query: str) -> str:
        encoded = quote_plus(query)
        return self.search_url if self.fixed_query else self.search_url.format(query=encoded)


@dataclass(frozen=True)
class PaperRecord:
    record_id: str
    title: str
    authors: str
    abstract: str
    published: str
    year: int | None
    url: str
    pdf_url: str
    doi: str
    source: str
    query: str
    collected_at: str


@dataclass(frozen=True)
class SourceRun:
    source: str
    status: str
    url: str
    records: int
    error: str | None = None


class TradingResearchSpider(Spider):
    """Polite multi-source metadata crawler built on Scrapling's scheduler."""

    name = "trading_research"
    robots_txt_obey = True
    concurrent_requests = 4
    concurrent_requests_per_domain = 1
    download_delay = 2.0
    max_blocked_retries = 2
    logging_level = logging.INFO

    def __init__(
        self,
        *,
        source_names: Sequence[str],
        query: str,
        collected_at: str,
        max_results_per_source: int,
        timeout_seconds: float,
        delay_seconds: float,
        concurrent_requests: int,
        max_blocked_retries: int,
        crawldir: Path | None = None,
        checkpoint_interval: float = 300.0,
        development_cache_dir: Path | None = None,
    ) -> None:
        self.source_specs = {name: SOURCES[name] for name in source_names}
        self.query = query
        self.collected_at = collected_at
        self.max_results_per_source = max_results_per_source
        self.timeout_seconds = timeout_seconds
        self.download_delay = delay_seconds
        self.concurrent_requests = concurrent_requests
        self.max_blocked_retries = max_blocked_retries
        self.start_urls = [spec.url_for(query) for spec in self.source_specs.values()]
        self.allowed_domains = {urlparse(url).netloc for url in self.start_urls}
        self.development_mode = development_cache_dir is not None
        self.development_cache_dir = str(development_cache_dir) if development_cache_dir else None
        self.responded_sources: set[str] = set()
        self.source_errors: dict[str, str] = {}
        self._seen_records: set[str] = set()
        super().__init__(crawldir=crawldir, interval=checkpoint_interval)

    async def start_requests(self):
        for source_name, spec in self.source_specs.items():
            yield Request(
                spec.url_for(self.query),
                callback=self.parse,
                meta={"source": source_name},
                timeout=self.timeout_seconds,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
            )

    async def parse(self, response: Response):
        source_name = str(response.meta["source"])
        self.responded_sources.add(source_name)
        records = parse_source_response(
            response,
            spec=self.source_specs[source_name],
            query=self.query,
            collected_at=self.collected_at,
            limit=self.max_results_per_source,
        )
        for record in records:
            yield asdict(record)

    async def on_scraped_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        key = str(item.get("doi", "")).lower()
        key = key or canonical_url(str(item.get("url", "")))
        key = key or normalize_text(item.get("title", "")).lower()
        if not key or key in self._seen_records:
            return None
        self._seen_records.add(key)
        return item

    async def on_error(self, request: Request, error: Exception) -> None:
        source_name = str(request.meta.get("source", "unknown"))
        self.source_errors[source_name] = str(error)
        self.logger.error("Failed %s: %s", source_name, error)


SOURCES: dict[str, SourceSpec] = {
    "arxiv": SourceSpec(
        name="arxiv",
        search_url=(
            "https://api.openalex.org/works?search={query}"
            "&filter=locations.source.id:S4306400194&per-page=50"
        ),
        item_selectors=(),
        title_selectors=(),
        link_selectors=(),
        parser="openalex_arxiv",
    ),
    "ssrn": SourceSpec(
        name="ssrn",
        search_url="https://papers.ssrn.com/sol3/results.cfm?txtKey_Words={query}",
        item_selectors=(".search-result", ".result-item", ".paper"),
        title_selectors=(".title", "h2", "h3"),
        link_selectors=("a[href*='abstract_id']",),
        author_selectors=(".authors", ".author"),
        abstract_selectors=(".abstract", ".description"),
        date_selectors=(".date", ".publication-date"),
    ),
    "repec": SourceSpec(
        name="repec",
        search_url="https://api.openalex.org/works?search={query}&per-page=100",
        item_selectors=(),
        title_selectors=(),
        link_selectors=(),
        parser="openalex_repec",
    ),
    "researchgate": SourceSpec(
        name="researchgate",
        search_url="https://api.openalex.org/works?search={query}&per-page=100",
        item_selectors=(),
        title_selectors=(),
        link_selectors=(),
        parser="openalex_researchgate",
    ),
    "nber": SourceSpec(
        name="nber",
        search_url="https://www.nber.org/api/v1/search?page=1&perPage=50&q={query}",
        item_selectors=(),
        title_selectors=(),
        link_selectors=(),
        parser="nber_json",
    ),
    "quantpedia": SourceSpec(
        name="quantpedia",
        search_url="https://quantpedia.com/?s={query}",
        item_selectors=("article", ".search-result", ".strategy"),
        title_selectors=(".entry-title", "h2", "h3"),
        link_selectors=("a[href]",),
        abstract_selectors=(".entry-summary", ".excerpt", "p"),
        date_selectors=("time", ".date"),
    ),
    "robeco": SourceSpec(
        name="robeco",
        search_url="https://www.robeco.com/en-int/search?q={query}",
        item_selectors=("article", ".search-result", ".card"),
        title_selectors=("h2", "h3", ".title"),
        link_selectors=("a[href]",),
        author_selectors=(".author",),
        abstract_selectors=(".description", ".summary", "p"),
        date_selectors=("time", ".date"),
    ),
    "oxford_man": SourceSpec(
        name="oxford_man",
        search_url="https://oxford-man.ox.ac.uk/selected-publications/",
        item_selectors=("article", ".publication", "li"),
        title_selectors=("h2", "h3", "h4", ".title", "a"),
        link_selectors=("a[href]",),
        author_selectors=(".author", ".authors"),
        abstract_selectors=(".abstract", ".description", "p"),
        date_selectors=("time", ".date", ".year"),
        pdf_selectors=("a[href$='.pdf']",),
        fixed_query=True,
        parser="oxford_links",
    ),
}

DEFAULT_SOURCES = ("arxiv", "repec", "nber", "oxford_man", "robeco")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    collected_at = datetime.now(tz=UTC).isoformat()
    spider = TradingResearchSpider(
        source_names=args.sources,
        query=args.query,
        collected_at=collected_at,
        max_results_per_source=args.max_results_per_source,
        timeout_seconds=args.timeout_seconds,
        delay_seconds=args.delay_seconds,
        concurrent_requests=args.concurrent_requests,
        max_blocked_retries=args.max_blocked_retries,
        crawldir=args.checkpoint_dir,
        checkpoint_interval=args.checkpoint_interval,
        development_cache_dir=args.development_cache_dir,
    )
    result = spider.start(use_uvloop=args.use_uvloop)
    records = [PaperRecord(**item) for item in result.items]
    runs = source_runs(spider, records, paused=result.paused)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or f"trading_research_{datetime.now(tz=UTC):%Y%m%d_%H%M%S}"
    jsonl_path = args.output_dir / f"{stem}.jsonl"
    csv_path = args.output_dir / f"{stem}.csv"
    manifest_path = args.output_dir / f"{stem}_manifest.json"
    result.items.to_jsonl(jsonl_path)
    write_csv(csv_path, records)
    manifest_path.write_text(
        json.dumps(
            {
                "query": args.query,
                "collected_at": collected_at,
                "record_count": len(records),
                "sources": [asdict(run) for run in runs],
                "crawl": {
                    "completed": result.completed,
                    "paused": result.paused,
                    "stats": result.stats.to_dict(),
                },
                "outputs": {"jsonl": str(jsonl_path), "csv": str(csv_path)},
                "policy": {
                    "robots_txt_obeyed": True,
                    "metadata_only": True,
                    "paywall_bypass": False,
                    "user_agent": USER_AGENT,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print_summary(records, runs, jsonl_path, csv_path, manifest_path)
    return 1 if not records and any(run.status in {"error", "not_fetched"} for run in runs) else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape public metadata for academic trading-strategy research using Scrapling."
    )
    parser.add_argument(
        "--query",
        default="trading strategy transaction costs Sharpe ratio",
        help="Research search query.",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=tuple(SOURCES),
        default=DEFAULT_SOURCES,
        help=(
            "Sources to collect. SSRN and Quantpedia are opt-in because access is less predictable; "
            "ResearchGate is discovered through OpenAlex rather than scraped directly."
        ),
    )
    parser.add_argument("--max-results-per-source", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--concurrent-requests", type=int, default=4)
    parser.add_argument("--max-blocked-retries", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--name", default=None, help="Output filename stem.")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="Optional Scrapling checkpoint directory for pause/resume.",
    )
    parser.add_argument("--checkpoint-interval", type=float, default=300.0)
    parser.add_argument(
        "--development-cache-dir",
        type=Path,
        default=None,
        help="Cache responses while developing selectors; do not use for production collection.",
    )
    parser.add_argument("--use-uvloop", action="store_true")
    args = parser.parse_args(argv)
    if args.max_results_per_source <= 0:
        parser.error("--max-results-per-source must be positive")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds must be non-negative")
    if args.concurrent_requests <= 0:
        parser.error("--concurrent-requests must be positive")
    if args.max_blocked_retries < 0:
        parser.error("--max-blocked-retries must be non-negative")
    if args.checkpoint_interval < 0:
        parser.error("--checkpoint-interval must be non-negative")
    return args


def parse_source_response(
    response: Any,
    *,
    spec: SourceSpec,
    query: str,
    collected_at: str,
    limit: int,
) -> list[PaperRecord]:
    if spec.parser == "nber_json":
        return parse_nber_json(response, spec=spec, query=query, collected_at=collected_at, limit=limit)
    if spec.parser.startswith("openalex_"):
        repository = spec.parser.removeprefix("openalex_")
        return parse_openalex_json(
            response,
            spec=spec,
            repository=repository,
            query=query,
            collected_at=collected_at,
            limit=limit,
        )
    if spec.parser == "oxford_links":
        return parse_oxford_links(response, spec=spec, query=query, collected_at=collected_at, limit=limit)

    items = first_nonempty_selection(response, spec.item_selectors)
    records: list[PaperRecord] = []
    query_terms = meaningful_query_terms(query)
    for item in items:
        title = first_text(item, spec.title_selectors)
        href = first_attribute(item, spec.link_selectors, "href")
        if not title or not href:
            continue
        abstract = first_text(item, spec.abstract_selectors)
        haystack = f"{title} {abstract}".lower()
        if spec.fixed_query and query_terms and not any(term in haystack for term in query_terms):
            continue
        url = response.urljoin(href) if hasattr(response, "urljoin") else urljoin(str(response.url), href)
        published = first_text(item, spec.date_selectors)
        pdf_href = first_attribute(item, spec.pdf_selectors, "href")
        pdf_url = urljoin(url, pdf_href) if pdf_href else ""
        doi_match = DOI_RE.search(f"{url} {abstract}")
        year_match = YEAR_RE.search(published)
        record_key = f"{spec.name}|{normalize_text(title).lower()}|{url}"
        records.append(
            PaperRecord(
                record_id=hashlib.sha256(record_key.encode("utf-8")).hexdigest()[:24],
                title=title,
                authors=first_text(item, spec.author_selectors),
                abstract=abstract,
                published=published,
                year=int(year_match.group()) if year_match else None,
                url=url,
                pdf_url=pdf_url,
                doi=doi_match.group().rstrip(".,;)") if doi_match else "",
                source=spec.name,
                query=query,
                collected_at=collected_at,
            )
        )
        if len(records) >= limit:
            break
    return records


def parse_nber_json(
    response: Any,
    *,
    spec: SourceSpec,
    query: str,
    collected_at: str,
    limit: int,
) -> list[PaperRecord]:
    payload = json.loads(bytes(response.body))
    records: list[PaperRecord] = []
    for item in payload.get("results", []):
        if item.get("type") != "working_paper":
            continue
        title = normalize_text(item.get("title"))
        href = normalize_text(item.get("url"))
        if not title or not href:
            continue
        authors = ", ".join(strip_html(author) for author in item.get("authors") or [])
        published = normalize_text(item.get("displaydate") or item.get("publisheddate"))
        year_match = YEAR_RE.search(published)
        url = urljoin(str(response.url), href)
        records.append(
            make_record(
                spec=spec,
                title=title,
                authors=authors,
                abstract=normalize_text(item.get("abstract")),
                published=published,
                year=int(year_match.group()) if year_match else None,
                url=url,
                pdf_url="",
                doi="",
                query=query,
                collected_at=collected_at,
            )
        )
        if len(records) >= limit:
            break
    return records


def parse_openalex_json(
    response: Any,
    *,
    spec: SourceSpec,
    repository: str,
    query: str,
    collected_at: str,
    limit: int,
) -> list[PaperRecord]:
    payload = json.loads(bytes(response.body))
    records: list[PaperRecord] = []
    for item in payload.get("results", []):
        locations = item.get("locations") or []
        repository_locations = [
            location
            for location in locations
            if repository_location(repository, location)
        ]
        if not repository_locations:
            continue
        title = normalize_text(item.get("display_name") or item.get("title"))
        if not title:
            continue
        location = repository_locations[0]
        url = normalize_text(location.get("landing_page_url") or item.get("doi") or item.get("id"))
        pdf_url = normalize_text(location.get("pdf_url"))
        authors = ", ".join(
            normalize_text(authorship.get("author", {}).get("display_name"))
            for authorship in item.get("authorships") or []
            if normalize_text(authorship.get("author", {}).get("display_name"))
        )
        year = item.get("publication_year")
        doi = normalize_text(item.get("doi")).removeprefix("https://doi.org/")
        records.append(
            make_record(
                spec=spec,
                title=title,
                authors=authors,
                abstract=rebuild_openalex_abstract(item.get("abstract_inverted_index")),
                published=normalize_text(item.get("publication_date")),
                year=int(year) if isinstance(year, int) else None,
                url=url,
                pdf_url=pdf_url,
                doi=doi,
                query=query,
                collected_at=collected_at,
            )
        )
        if len(records) >= limit:
            break
    return records


def parse_oxford_links(
    response: Any,
    *,
    spec: SourceSpec,
    query: str,
    collected_at: str,
    limit: int,
) -> list[PaperRecord]:
    records: list[PaperRecord] = []
    query_terms = meaningful_query_terms(query)
    allowed_hosts = ("arxiv.org", "ssrn.com", "tandfonline.com", "doi.org")
    for link in response.css("a[href]"):
        title = normalize_text(link.get_all_text(separator=" ", strip=True))
        href = normalize_text(link.attrib.get("href"))
        if not title or not href or not any(host in urlparse(href).netloc.lower() for host in allowed_hosts):
            continue
        if query_terms and not any(term in title.lower() for term in query_terms):
            continue
        doi_match = DOI_RE.search(href)
        records.append(
            make_record(
                spec=spec,
                title=title,
                authors="",
                abstract="",
                published="",
                year=None,
                url=href,
                pdf_url=href if ".pdf" in href.lower() else "",
                doi=doi_match.group().rstrip(".,;)") if doi_match else "",
                query=query,
                collected_at=collected_at,
            )
        )
        if len(records) >= limit:
            break
    return deduplicate_records(records)


def make_record(
    *,
    spec: SourceSpec,
    title: str,
    authors: str,
    abstract: str,
    published: str,
    year: int | None,
    url: str,
    pdf_url: str,
    doi: str,
    query: str,
    collected_at: str,
) -> PaperRecord:
    record_key = f"{spec.name}|{normalize_text(title).lower()}|{url}"
    return PaperRecord(
        record_id=hashlib.sha256(record_key.encode("utf-8")).hexdigest()[:24],
        title=title,
        authors=authors,
        abstract=abstract,
        published=published,
        year=year,
        url=url,
        pdf_url=pdf_url,
        doi=doi,
        source=spec.name,
        query=query,
        collected_at=collected_at,
    )


def repository_location(repository: str, location: dict[str, Any]) -> bool:
    source = location.get("source") or {}
    source_id = normalize_text(source.get("id"))
    landing_page = normalize_text(location.get("landing_page_url")).lower()
    if repository == "arxiv":
        return source_id.endswith("/S4306400194") or "arxiv.org/" in landing_page
    if repository == "repec":
        return "repec.org/" in landing_page
    if repository == "researchgate":
        return "researchgate.net/" in landing_page
    return False


def rebuild_openalex_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            positioned.extend((int(position), str(word)) for position in positions)
    return " ".join(word for _, word in sorted(positioned))


def strip_html(value: Any) -> str:
    return normalize_text(re.sub(r"<[^>]+>", "", str(value or "")))


def first_nonempty_selection(node: Any, selectors: Iterable[str]) -> list[Any]:
    for selector in selectors:
        matches = list(node.css(selector))
        if matches:
            return matches
    return []


def first_text(node: Any, selectors: Iterable[str]) -> str:
    for selector in selectors:
        matches = node.css(selector)
        if matches:
            text = normalize_text(matches[0].get_all_text(separator=" ", strip=True))
            if text:
                return text
    return ""


def first_attribute(node: Any, selectors: Iterable[str], attribute: str) -> str:
    for selector in selectors:
        matches = node.css(selector)
        if matches:
            value = matches[0].attrib.get(attribute, "")
            if value:
                return str(value).strip()
    return ""


def normalize_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def meaningful_query_terms(query: str) -> set[str]:
    return {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", query)
        if term.lower() not in {"with", "from", "that", "this", "ratio"}
    }


def deduplicate_records(records: Iterable[PaperRecord]) -> list[PaperRecord]:
    unique: list[PaperRecord] = []
    seen: set[str] = set()
    for record in records:
        key = record.doi.lower() or canonical_url(record.url) or normalize_text(record.title).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def source_runs(
    spider: TradingResearchSpider,
    records: Sequence[PaperRecord],
    *,
    paused: bool,
) -> list[SourceRun]:
    counts: dict[str, int] = {name: 0 for name in spider.source_specs}
    for record in records:
        counts[record.source] += 1
    runs: list[SourceRun] = []
    for source_name, spec in spider.source_specs.items():
        error = spider.source_errors.get(source_name)
        if error:
            status = "error"
        elif source_name in spider.responded_sources:
            status = "ok" if counts[source_name] else "empty"
        else:
            status = "not_fetched"
            error = (
                "crawl paused before this source completed"
                if paused
                else "request was blocked after retries or disallowed by robots.txt"
            )
        runs.append(
            SourceRun(
                source=source_name,
                status=status,
                url=spec.url_for(spider.query),
                records=counts[source_name],
                error=error,
            )
        )
    return runs


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def write_csv(path: Path, records: Sequence[PaperRecord]) -> None:
    fieldnames = list(PaperRecord.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)


def print_summary(
    records: Sequence[PaperRecord],
    runs: Sequence[SourceRun],
    jsonl_path: Path,
    csv_path: Path,
    manifest_path: Path,
) -> None:
    print(f"Collected {len(records)} unique research records")
    for run in runs:
        detail = f": {run.error}" if run.error else ""
        print(f"- {run.source}: {run.status} ({run.records}){detail}")
    print(f"Wrote {jsonl_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
