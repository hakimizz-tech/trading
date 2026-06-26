import unittest
from types import SimpleNamespace

from execution.aiomql_base import (
    extract_order_check,
    order_cancel_result_from_source,
    pending_order_from_source,
)


class AiomqlOrderBridgeTests(unittest.TestCase):
    def test_extracts_order_check_with_margin_and_expected_profit(self) -> None:
        check = extract_order_check(
            check_result={
                "retcode": 0,
                "margin": 25.0,
                "profit": 50.0,
                "comment": "Done",
            },
            symbol="EURUSD",
            direction="long",
            volume=0.1,
            parameters={"entry_price": 1.1, "expected_loss": -20.0},
        )

        self.assertTrue(check.allowed)
        self.assertEqual(check.symbol, "EURUSD")
        self.assertEqual(check.direction, "long")
        self.assertEqual(check.margin, 25.0)
        self.assertEqual(check.expected_profit, 50.0)
        self.assertEqual(check.expected_loss, -20.0)

    def test_rejects_order_check_when_retcode_and_comment_do_not_confirm(self) -> None:
        check = extract_order_check(
            check_result={"retcode": 10019, "comment": "No money"},
            symbol="EURUSD",
            direction="short",
            volume=0.1,
        )

        self.assertFalse(check.allowed)
        self.assertEqual(check.retcode, 10019)

    def test_normalizes_pending_order_object(self) -> None:
        order = pending_order_from_source(
            SimpleNamespace(
                ticket=123,
                symbol="EURUSD",
                type="ORDER_TYPE_BUY_LIMIT",
                volume_current=0.1,
                price_open=1.1,
                sl=1.095,
                tp=1.11,
                magic=260617,
                comment="bollinger-adaptive",
            ),
            strategy="bollinger-adaptive",
        )

        self.assertIsNotNone(order)
        assert order is not None
        self.assertEqual(order.ticket, "123")
        self.assertEqual(order.direction, "long")
        self.assertEqual(order.stop_loss, 1.095)
        self.assertEqual(order.strategy, "bollinger-adaptive")

    def test_normalizes_cancel_result(self) -> None:
        result = order_cancel_result_from_source({"order": 123, "retcode": 10009, "comment": "Done"}, ticket="123")

        self.assertTrue(result.cancelled)
        self.assertEqual(result.ticket, "123")
        self.assertEqual(result.retcode, 10009)


if __name__ == "__main__":
    unittest.main()
