"""News event signal module for strategies and agents."""

from News.core import (
    DEFAULT_EVENT_PATTERNS,
    ExtractedNewsEvent,
    NewsArticle,
    NewsEventPattern,
    NewsSignalConfig,
    NewsSignalResult,
    SentimentBreakdown,
    build_news_signals,
    decision_from_score,
    extract_events_from_text,
    merge_news_features,
    score_text_sentiment,
    score_text_sentiment_components,
)
from News.features import (
    NewsFeatureConfig,
    build_news_feature_matrix,
    create_forward_return_labels,
    merge_news_features_and_labels,
)

__all__ = [
    "DEFAULT_EVENT_PATTERNS",
    "ExtractedNewsEvent",
    "NewsArticle",
    "NewsEventPattern",
    "NewsFeatureConfig",
    "NewsSignalConfig",
    "NewsSignalResult",
    "SentimentBreakdown",
    "build_news_feature_matrix",
    "build_news_signals",
    "create_forward_return_labels",
    "decision_from_score",
    "extract_events_from_text",
    "merge_news_features_and_labels",
    "merge_news_features",
    "score_text_sentiment",
    "score_text_sentiment_components",
]
