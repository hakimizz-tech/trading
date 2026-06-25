import unittest

from execution.adapters import BrokerAdapter, BrokerDataAdapter, BrokerExecutionAdapter
from execution.state import AccountSnapshot, BrokerFill, BrokerSnapshot, SymbolContract


class ExecutionAdapterContractTests(unittest.TestCase):
    def test_async_adapter_satisfies_runtime_protocols(self) -> None:
        adapter = FakeBrokerAdapter()

        self.assertIsInstance(adapter, BrokerDataAdapter)
        self.assertIsInstance(adapter, BrokerExecutionAdapter)
        self.assertIsInstance(adapter, BrokerAdapter)


class FakeBrokerAdapter:
    async def snapshot(self, *, symbol: str, strategy: str | None = None) -> BrokerSnapshot:
        return BrokerSnapshot(
            account=AccountSnapshot(equity=10_000.0, balance=10_000.0, free_margin=9_000.0),
            contract=SymbolContract(symbol=symbol, point=0.00001, pip_size=0.0001, tick_value=1.0, min_lot=0.01, max_lot=1.0, lot_step=0.01),
        )

    async def history(self, *, date_from: object, date_to: object, group: str | None = None) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        return ([{"deal": 1}], [{"order": 2}])

    async def place_market_order(
        self,
        *,
        symbol: str,
        direction: str,
        volume: float,
        parameters: dict[str, object] | None = None,
    ) -> BrokerFill:
        return BrokerFill(external_id="fill-1", symbol=symbol, direction=direction, volume=volume, price=1.1)


if __name__ == "__main__":
    unittest.main()
