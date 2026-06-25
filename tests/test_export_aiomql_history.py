import unittest
from datetime import datetime, timezone

from pathlib import Path

from scripts.export_aiomql_history import _collect_history, _configure_aiomql


class ExportAiomqlHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_history_uses_account_context_and_initialize(self) -> None:
        aiomql = FakeAiomqlWithInitialize()

        deals, orders = await _collect_history(aiomql, {"group": "*USD*"})

        self.assertTrue(aiomql.account_entered)
        self.assertEqual(deals[0]["deal"], 1)
        self.assertEqual(orders[0]["order"], 2)
        self.assertEqual(aiomql.history_kwargs, {"group": "*USD*"})

    async def test_collect_history_supports_docs_init_method(self) -> None:
        aiomql = FakeAiomqlWithInit()
        date_from = datetime(2026, 6, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 6, 2, tzinfo=timezone.utc)

        deals, orders = await _collect_history(
            aiomql,
            {"date_from": date_from, "date_to": date_to},
            date_from=date_from,
            date_to=date_to,
            use_account_context=False,
        )

        self.assertEqual(deals[0]["deal"], 30)
        self.assertEqual(orders[0]["order"], 40)
        self.assertEqual(aiomql.history.init_args, (date_from, date_to))

    async def test_collect_history_supports_creator_total_methods(self) -> None:
        aiomql = FakeAiomqlWithTotalMethods()

        deals, orders = await _collect_history(aiomql, {}, use_account_context=False)

        self.assertEqual(deals[0]["deal"], 10)
        self.assertEqual(orders[0]["order"], 20)
        self.assertTrue(aiomql.history.deals_total_called)
        self.assertTrue(aiomql.history.orders_total_called)

    def test_config_uses_aiomql_singleton_reload_pattern(self) -> None:
        aiomql = FakeAiomqlConfig()

        _configure_aiomql(aiomql, Path("config.json"))

        self.assertEqual(aiomql.config_calls, [{"filename": "config.json", "reload": True}])


class FakeAccount:
    def __init__(self, owner: "FakeAiomqlWithInitialize") -> None:
        self.owner = owner

    async def __aenter__(self) -> "FakeAccount":
        self.owner.account_entered = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.owner.account_exited = True


class FakeAiomqlWithInitialize:
    def __init__(self) -> None:
        self.account_entered = False
        self.account_exited = False
        self.history_kwargs: dict[str, object] = {}

    def Account(self) -> FakeAccount:
        return FakeAccount(self)

    def History(self, **kwargs: object) -> "FakeHistoryWithInitialize":
        self.history_kwargs = kwargs
        return FakeHistoryWithInitialize()


class FakeHistoryWithInitialize:
    def __init__(self) -> None:
        self.deals: list[dict[str, object]] = []
        self.orders: list[dict[str, object]] = []

    async def initialize(self) -> None:
        self.deals = [{"deal": 1, "symbol": "EURUSD"}]
        self.orders = [{"order": 2, "symbol": "EURUSD"}]


class FakeAiomqlWithTotalMethods:
    def __init__(self) -> None:
        self.history = FakeHistoryWithTotalMethods()

    def History(self, **kwargs: object) -> "FakeHistoryWithTotalMethods":
        return self.history


class FakeAiomqlWithInit:
    def __init__(self) -> None:
        self.history = FakeHistoryWithInit()

    def History(self, **kwargs: object) -> "FakeHistoryWithInit":
        return self.history


class FakeHistoryWithInit:
    def __init__(self) -> None:
        self.init_args: tuple[datetime, datetime] | None = None
        self.deals: list[dict[str, object]] = []
        self.orders: list[dict[str, object]] = []

    async def init(self, date_from: datetime, date_to: datetime) -> None:
        self.init_args = (date_from, date_to)
        self.deals = [{"deal": 30, "symbol": "ETHUSD"}]
        self.orders = [{"order": 40, "symbol": "ETHUSD"}]


class FakeAiomqlConfig:
    def __init__(self) -> None:
        self.config_calls: list[dict[str, object]] = []

    def Config(self, **kwargs: object) -> None:
        self.config_calls.append(kwargs)


class FakeHistoryWithTotalMethods:
    def __init__(self) -> None:
        self.deals_total_called = False
        self.orders_total_called = False
        self.deals: list[dict[str, object]] = []
        self.orders: list[dict[str, object]] = []

    async def deals_total(self) -> int:
        self.deals_total_called = True
        self.deals = [{"deal": 10, "symbol": "BTCUSD"}]
        return len(self.deals)

    async def orders_total(self) -> int:
        self.orders_total_called = True
        self.orders = [{"order": 20, "symbol": "BTCUSD"}]
        return len(self.orders)


if __name__ == "__main__":
    unittest.main()
