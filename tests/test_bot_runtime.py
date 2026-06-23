from __future__ import annotations

from types import SimpleNamespace

import pytest

import bot
from bot_config import BotSettings, SessionSpec, StrategySpec, TrackerSpec


def test_load_aiomql_raises_clear_error_when_package_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import_module(name: str):
        if name == "aiomql":
            raise ImportError("missing")
        raise AssertionError(name)

    monkeypatch.setattr(bot, "import_module", fake_import_module)

    with pytest.raises(RuntimeError, match="aiomql is not available"):
        bot._load_aiomql()


def test_preflight_mt5_symbols_selects_hidden_symbols() -> None:
    mt5 = FakeMt5({"EURUSD": FakeSymbolInfo(visible=False)})
    settings = BotSettings(strategies=[StrategySpec(name="BB", type="bollinger", symbols=["EURUSD"])])

    bot.preflight_mt5_symbols(settings, mt5=mt5)

    assert mt5.initialized
    assert mt5.shutdown_called
    assert mt5.selected == ["EURUSD"]


def test_preflight_mt5_symbols_reports_missing_symbols() -> None:
    mt5 = FakeMt5({})
    settings = BotSettings(strategies=[StrategySpec(name="BB", type="bollinger", symbols=["EURUSDm"])])

    with pytest.raises(RuntimeError, match="EURUSDm: not found"):
        bot.preflight_mt5_symbols(settings, mt5=mt5)

    assert mt5.shutdown_called


def test_build_sessions_constructs_aiomql_sessions() -> None:
    aiomql = SimpleNamespace(Session=FakeSession, Sessions=FakeSessions)
    specs = [SessionSpec(name="london", start="07:00", end="17:00", timezone="UTC", on_end="close_loss")]

    sessions = bot._build_sessions(aiomql, specs)

    assert isinstance(sessions, FakeSessions)
    assert sessions.sessions[0].kwargs["name"] == "london"
    assert sessions.sessions[0].kwargs["start"].hour == 7
    assert sessions.sessions[0].kwargs["end"].hour == 17
    assert sessions.sessions[0].kwargs["timezone"] == "UTC"
    assert sessions.sessions[0].kwargs["on_end"] == "close_loss"


def test_configure_aiomql_applies_config_settings() -> None:
    aiomql = SimpleNamespace(Config=FakeConfig)
    settings = BotSettings(aiomql_config={"trade_record_mode": "sql", "root": "trade_results"})

    config = bot.configure_aiomql(aiomql, settings)

    assert isinstance(config, FakeConfig)
    assert config.kwargs == {"trade_record_mode": "sql", "root": "trade_results"}


def test_add_configured_trackers_schedules_enabled_trackers() -> None:
    fake_bot = FakeBot()
    trackers = [
        TrackerSpec(name="exit_at_profit", enabled=False),
        TrackerSpec(name="exit_at_points", enabled=True, interval=7, on_separate_thread=True, params={"points": 50}),
    ]

    bot.add_configured_trackers(fake_bot, trackers)

    assert len(fake_bot.coroutines) == 1
    scheduled = fake_bot.coroutines[0]
    assert callable(scheduled["coroutine"])
    assert scheduled["interval"] == 7
    assert scheduled["on_separate_thread"] is True


def test_start_bot_uses_async_aiomql_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bot = FakeAsyncBot()
    monkeypatch.setattr(bot, "build_bot", lambda settings: fake_bot)

    import asyncio

    asyncio.run(bot.start_bot(BotSettings()))

    assert fake_bot.started is True


class FakeSymbolInfo:
    def __init__(self, *, visible: bool) -> None:
        self.visible = visible


class FakeMt5:
    def __init__(self, symbols: dict[str, FakeSymbolInfo]) -> None:
        self.symbols = symbols
        self.initialized = False
        self.shutdown_called = False
        self.selected: list[str] = []

    def initialize(self) -> bool:
        self.initialized = True
        return True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def symbol_info(self, symbol: str) -> FakeSymbolInfo | None:
        return self.symbols.get(symbol)

    def symbol_select(self, symbol: str, enabled: bool) -> bool:
        if enabled and symbol in self.symbols:
            self.selected.append(symbol)
            self.symbols[symbol].visible = True
            return True
        return False

    def last_error(self) -> tuple[int, str]:
        return (0, "OK")


class FakeSession:
    def __init__(self, **kwargs: str) -> None:
        self.kwargs = kwargs


class FakeSessions:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = sessions


class FakeConfig:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeBot:
    def __init__(self) -> None:
        self.coroutines: list[dict[str, object]] = []

    def add_coroutine(self, **kwargs: object) -> None:
        self.coroutines.append(kwargs)


class FakeAsyncBot:
    def __init__(self) -> None:
        self.started = False

    async def start(self) -> None:
        self.started = True
