#!/usr/bin/env python3
"""Compare journal, ledger, and optional broker deal exports."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from accounting import TradeLedger
from journal import TradeJournal


def main() -> None:
    args = _parse_args()
    journal_trades = _journal_trades(str(args.journal_db))
    ledger_transactions = _ledger_transactions(str(args.ledger_db))
    broker_ids = _broker_external_ids(args.broker_deals_csv) if args.broker_deals_csv else set()

    ledger_external_ids = {str(tx["external_id"]) for tx in ledger_transactions if tx.get("external_id")}
    confirmed_journal = [
        trade
        for trade in journal_trades
        if trade.get("status") in {"filled", "partially_filled", "closed"}
    ]
    journal_broker_ids = {
        str(metadata["broker_external_id"])
        for trade in confirmed_journal
        for metadata in [_metadata(trade)]
        if metadata.get("broker_external_id")
    }

    report = {
        "journal_trades": len(journal_trades),
        "journal_confirmed_trades": len(confirmed_journal),
        "ledger_transactions": len(ledger_transactions),
        "ledger_external_ids": len(ledger_external_ids),
        "confirmed_journal_ids_missing_from_ledger": sorted(journal_broker_ids - ledger_external_ids),
        "ledger_ids_missing_from_broker_export": sorted(ledger_external_ids - broker_ids) if broker_ids else [],
        "broker_ids_missing_from_ledger": sorted(broker_ids - ledger_external_ids) if broker_ids else [],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


def _journal_trades(database: str) -> list[dict[str, Any]]:
    if "://" not in database and not Path(database).exists():
        return []
    return TradeJournal(database).list_trades()


def _ledger_transactions(database: str) -> list[dict[str, Any]]:
    if "://" not in database and not Path(database).exists():
        return []
    return TradeLedger(database).list_transactions()


def _broker_external_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        id_column = _first_existing(columns, ("external_id", "deal_id", "deal", "ticket", "order"))
        if id_column is None:
            raise ValueError("broker CSV must contain one of: external_id, deal_id, deal, ticket, order")
        return {str(row[id_column]) for row in reader if row.get(id_column)}


def _first_existing(columns: Sequence[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    try:
        return json.loads(str(row.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        return {}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile trade journal, ledger, and optional broker deal export.")
    parser.add_argument("--journal-db", default="db/trade_journal.sqlite")
    parser.add_argument("--ledger-db", default="db/trade_accounting.sqlite")
    parser.add_argument("--broker-deals-csv", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()
