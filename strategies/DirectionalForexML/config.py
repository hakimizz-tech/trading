"""Configuration objects for Directional Forex ML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FeatureSet = Literal["paper_technical", "extended"]

ModelName = Literal[
    "logistic",
    "logistic_madl",
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "adaboost",
    "xgboost",
    "mlp",
]


@dataclass(frozen=True)
class DirectionalForexMLConfig:
    """Configuration for the paper-inspired forex ML classifier."""

    model_name: ModelName = "logistic_madl"
    feature_set: FeatureSet = "paper_technical"
    horizon: int = 1
    probability_threshold: float = 0.54
    threshold_min: float = 0.50
    threshold_max: float = 0.60
    threshold_step: float = 0.02
    expected_move_window: int = 20
    cost_buffer_pct: float = 0.0
    initial_cash: float = 10_000.0
    annualization: int = 252
    train_fraction: float = 0.75
    cv_splits: int = 5
    random_search_iterations: int = 10
    enable_hyperparameter_search: bool = True
    random_state: int = 42
    max_iter: int = 1_000
    use_macro_features: bool = False

    def __post_init__(self) -> None:
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        if self.feature_set not in {"paper_technical", "extended"}:
            raise ValueError("feature_set must be 'paper_technical' or 'extended'")
        if not 0.5 <= self.probability_threshold < 1.0:
            raise ValueError("probability_threshold must be in [0.5, 1.0)")
        if not 0.5 <= self.threshold_min <= self.threshold_max < 1.0:
            raise ValueError("threshold_min and threshold_max must be in [0.5, 1.0)")
        if self.threshold_step <= 0:
            raise ValueError("threshold_step must be positive")
        if self.expected_move_window <= 1:
            raise ValueError("expected_move_window must be greater than 1")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not 0 < self.train_fraction < 1:
            raise ValueError("train_fraction must be in (0, 1)")
        if self.cv_splits < 2:
            raise ValueError("cv_splits must be at least 2")
        if self.random_search_iterations <= 0:
            raise ValueError("random_search_iterations must be positive")
