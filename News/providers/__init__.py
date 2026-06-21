"""Optional news data providers.

Provider modules normalize external feeds into the generic ``News.core`` data
model. They should stay optional so research and tests can run without API
credentials.
"""

from News.providers.forex_factory import (
    FOREX_FACTORY_WEEKLY_JSON_URL,
    FOREX_FACTORY_WEEKLY_XML_URL,
    ForexFactoryProviderError,
    build_forex_factory_export_url,
    fetch_forex_factory_weekly_export,
    forex_factory_to_signals,
    normalize_forex_factory_export,
)
from News.providers.google_news import (
    GOOGLE_NEWS_SEARCH_URL,
    GOOGLE_NEWS_TOP_STORIES_URL,
    GoogleNewsProviderError,
    build_google_news_rss_url,
    fetch_google_news_rss,
    google_news_to_signals,
    normalize_google_news_rss,
)
from News.providers.official_macro import (
    DEFAULT_OFFICIAL_MACRO_FEEDS,
    OfficialMacroFeed,
    OfficialMacroProviderError,
    fetch_default_official_macro_feeds,
    fetch_official_macro_feed,
    normalize_official_macro_feed,
    official_macro_to_signals,
)
from News.providers.okx import (
    OkxNewsProviderConfig,
    OkxNewsProviderError,
    build_okx_by_coin_command,
    build_okx_coin_sentiment_command,
    build_okx_coin_trend_command,
    build_okx_economic_calendar_command,
    build_okx_latest_command,
    build_okx_search_command,
    fetch_okx_coin_news,
    fetch_okx_coin_sentiment,
    fetch_okx_coin_trend,
    fetch_okx_economic_calendar,
    fetch_okx_latest_news,
    normalize_okx_coin_sentiment,
    normalize_okx_coin_trend,
    normalize_okx_economic_calendar,
    normalize_okx_news,
    okx_news_to_signals,
)
from News.providers.schema import CANONICAL_NEWS_COLUMNS, normalize_provider_records
from News.providers.yfinance_news import (
    YFinanceNewsProviderError,
    fetch_yfinance_news,
    normalize_yfinance_news,
    yfinance_news_to_signals,
)

__all__ = [
    "CANONICAL_NEWS_COLUMNS",
    "DEFAULT_OFFICIAL_MACRO_FEEDS",
    "FOREX_FACTORY_WEEKLY_JSON_URL",
    "FOREX_FACTORY_WEEKLY_XML_URL",
    "GOOGLE_NEWS_SEARCH_URL",
    "GOOGLE_NEWS_TOP_STORIES_URL",
    "ForexFactoryProviderError",
    "GoogleNewsProviderError",
    "OkxNewsProviderConfig",
    "OkxNewsProviderError",
    "OfficialMacroFeed",
    "OfficialMacroProviderError",
    "YFinanceNewsProviderError",
    "build_forex_factory_export_url",
    "build_google_news_rss_url",
    "build_okx_by_coin_command",
    "build_okx_coin_sentiment_command",
    "build_okx_coin_trend_command",
    "build_okx_economic_calendar_command",
    "build_okx_latest_command",
    "build_okx_search_command",
    "fetch_default_official_macro_feeds",
    "fetch_forex_factory_weekly_export",
    "fetch_google_news_rss",
    "fetch_official_macro_feed",
    "fetch_okx_coin_news",
    "fetch_okx_coin_sentiment",
    "fetch_okx_coin_trend",
    "fetch_okx_economic_calendar",
    "fetch_okx_latest_news",
    "fetch_yfinance_news",
    "forex_factory_to_signals",
    "google_news_to_signals",
    "normalize_forex_factory_export",
    "normalize_google_news_rss",
    "normalize_official_macro_feed",
    "normalize_okx_coin_sentiment",
    "normalize_okx_coin_trend",
    "normalize_okx_economic_calendar",
    "normalize_okx_news",
    "normalize_provider_records",
    "normalize_yfinance_news",
    "official_macro_to_signals",
    "okx_news_to_signals",
    "yfinance_news_to_signals",
]
