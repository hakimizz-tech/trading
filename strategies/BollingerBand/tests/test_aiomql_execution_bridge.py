import unittest

from strategies.BollingerBand.execution.aiomql_strategy import _broker_snapshot_from_sources, _extract_broker_fill


class AiomqlExecutionBridgeTests(unittest.TestCase):
    def test_broker_snapshot_from_duck_typed_sources(self) -> None:
        symbol = {
            "info": {
                "point": 0.00001,
                "trade_tick_value": 1.0,
                "volume_min": 0.01,
                "volume_max": 50.0,
                "volume_step": 0.01,
                "spread": 12.0,
            }
        }
        trader = {
            "account_info": {"equity": 10_000.0, "balance": 10_100.0, "margin_free": 8_000.0, "currency": "USD"},
            "positions": [
                {
                    "ticket": "123",
                    "symbol": "EURUSD",
                    "type": "BUY",
                    "volume": 0.1,
                    "price_open": 1.1,
                    "comment": "bollinger-adaptive",
                }
            ],
        }

        snapshot = _broker_snapshot_from_sources(
            symbol=symbol,
            trader=trader,
            strategy="bollinger-adaptive",
            fallback_symbol="EURUSD",
            fallback_spread=None,
            fallback_min_lot=None,
            fallback_max_lot=None,
            fallback_lot_step=None,
        )

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.account.currency, "USD")
        self.assertEqual(snapshot.contract.symbol, "EURUSD")
        self.assertEqual(snapshot.contract.tick_value, 10.0)
        self.assertEqual(snapshot.current_spread, 12.0)
        self.assertEqual(len(snapshot.open_positions), 1)

    def test_extract_broker_fill_for_confirmed_position_close(self) -> None:
        fill = _extract_broker_fill(
            order_result={
                "deal": "DEAL-42",
                "symbol": "XAUUSD",
                "volume": 0.2,
                "price": 2412.0,
                "profit": 75.0,
                "commission": -2.5,
                "swap": -0.5,
                "time": "2026-06-17T10:00:00Z",
            },
            trade_parameters={"entry_price": 2400.0, "volume": 0.2},
            symbol="XAUUSD",
            direction="long",
        )

        self.assertIsNotNone(fill)
        self.assertEqual(fill.external_id, "DEAL-42")
        self.assertEqual(fill.realized_pnl, 75.0)
        self.assertEqual(fill.commission, -2.5)
        self.assertEqual(fill.exit_price, 2412.0)


if __name__ == "__main__":
    unittest.main()
