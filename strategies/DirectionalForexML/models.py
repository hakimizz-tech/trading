"""Scikit-learn model training, prediction, and threshold utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.DirectionalForexML.config import DirectionalForexMLConfig, ModelName
from strategies.DirectionalForexML.costs import ForexCostSpec, cost_spec_for_symbol
from strategies.DirectionalForexML.features import compute_directional_features
from strategies.DirectionalForexML.labels import prepare_ml_dataset


@dataclass(frozen=True)
class DirectionalForexMLArtifact:
    """Trained model plus metadata needed for live/research inference."""

    model: Any
    feature_columns: tuple[str, ...]
    config: DirectionalForexMLConfig
    symbol: str
    cost_spec: ForexCostSpec
    model_name: str
    validation_score: float | None = None
    selected_threshold: float | None = None


def train_directional_forex_model(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    config: DirectionalForexMLConfig | None = None,
    macro: pd.DataFrame | None = None,
    cost_spec: ForexCostSpec | None = None,
) -> DirectionalForexMLArtifact:
    """Train a paper-style classifier and return an inference artifact."""
    cfg = config or DirectionalForexMLConfig()
    features, labels, forward_returns = prepare_ml_dataset(ohlcv, cfg, macro=macro)
    if len(features) < max(50, cfg.cv_splits * 10):
        raise ValueError("not enough rows to train directional forex model")

    if cfg.model_name == "logistic_madl":
        model, score = _fit_logistic_madl(features, labels, forward_returns, cfg)
    else:
        model = make_model(cfg.model_name, cfg)
        if cfg.enable_hyperparameter_search:
            model, score = _fit_randomized_search(model, features, labels, cfg)
        else:
            model.fit(features, labels)
            score = None

    probabilities = _predict_model_probabilities(model, features)
    thresholds = np.arange(cfg.threshold_min, cfg.threshold_max + cfg.threshold_step / 2.0, cfg.threshold_step)
    threshold, _ = optimize_probability_threshold(
        pd.Series(probabilities, index=features.index),
        forward_returns,
        thresholds=thresholds,
        min_trades=5,
    )
    return DirectionalForexMLArtifact(
        model=model,
        feature_columns=tuple(features.columns),
        config=cfg,
        symbol=symbol.upper(),
        cost_spec=cost_spec or cost_spec_for_symbol(symbol),
        model_name=cfg.model_name,
        validation_score=score,
        selected_threshold=threshold,
    )


def predict_directional_probabilities(
    ohlcv: pd.DataFrame,
    artifact: DirectionalForexMLArtifact,
    *,
    macro: pd.DataFrame | None = None,
) -> pd.Series:
    """Predict probability of an upward move over the configured horizon."""
    features = compute_directional_features(
        ohlcv,
        feature_set=artifact.config.feature_set,
        macro=macro,
        include_macro=artifact.config.use_macro_features,
    )
    features = features.reindex(columns=list(artifact.feature_columns)).dropna()
    if features.empty:
        return pd.Series(dtype=float, name="probability_up")
    probabilities = _predict_model_probabilities(artifact.model, features)
    return pd.Series(probabilities, index=features.index, name="probability_up")


def optimize_probability_threshold(
    probabilities: pd.Series,
    forward_returns: pd.Series,
    *,
    thresholds: np.ndarray | None = None,
    min_trades: int = 10,
) -> tuple[float, float]:
    """Find the long/short symmetric threshold that maximizes profit factor."""
    if thresholds is None:
        thresholds = np.arange(0.50, 0.76, 0.02)
    aligned = pd.concat([probabilities.rename("prob"), forward_returns.rename("ret")], axis=1).dropna()
    best_threshold = 0.5
    best_profit_factor = 0.0
    for threshold in thresholds:
        direction = pd.Series(0.0, index=aligned.index)
        direction.loc[aligned["prob"].ge(threshold)] = 1.0
        direction.loc[aligned["prob"].le(1.0 - threshold)] = -1.0
        selected = direction.ne(0.0)
        if int(selected.sum()) < min_trades:
            continue
        returns = direction[selected] * aligned.loc[selected, "ret"]
        gross_profit = returns[returns > 0].sum()
        gross_loss = abs(returns[returns < 0].sum())
        profit_factor = 0.0 if gross_loss == 0 else float(gross_profit / gross_loss)
        if profit_factor > best_profit_factor:
            best_threshold = float(threshold)
            best_profit_factor = profit_factor
    return best_threshold, best_profit_factor


def madl_score(y_true: pd.Series, y_pred: Any, forward_returns: pd.Series) -> float:
    """Profit-aware directional score; higher is better."""
    predicted_direction = np.where(np.asarray(y_pred).astype(int) == 1, 1.0, -1.0)
    realized = np.asarray(forward_returns, dtype=float)
    signed_profit = np.sign(realized * predicted_direction) * np.abs(realized)
    return float(np.nanmean(signed_profit))


def make_model(model_name: ModelName, cfg: DirectionalForexMLConfig) -> Any:
    """Create the scikit-learn model/pipeline for a named paper model."""
    from sklearn.ensemble import AdaBoostClassifier, GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.tree import DecisionTreeClassifier

    if model_name == "logistic":
        estimator = LogisticRegression(max_iter=cfg.max_iter, random_state=cfg.random_state)
        return Pipeline([("scale", StandardScaler()), ("model", estimator)])
    if model_name == "decision_tree":
        return DecisionTreeClassifier(max_depth=4, min_samples_leaf=10, random_state=cfg.random_state)
    if model_name == "random_forest":
        return RandomForestClassifier(n_estimators=100, max_depth=5, min_samples_leaf=10, random_state=cfg.random_state)
    if model_name == "gradient_boosting":
        return GradientBoostingClassifier(n_estimators=100, learning_rate=0.05, max_depth=2, random_state=cfg.random_state)
    if model_name == "adaboost":
        return AdaBoostClassifier(n_estimators=100, learning_rate=0.05, random_state=cfg.random_state)
    if model_name == "xgboost":
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise RuntimeError(
                "xgboost is required for model_name='xgboost'. Install it with "
                "`python -m pip install xgboost` or use another model."
            ) from exc
        return XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=cfg.random_state,
        )
    if model_name == "mlp":
        estimator = MLPClassifier(hidden_layer_sizes=(16,), max_iter=cfg.max_iter, random_state=cfg.random_state)
        return Pipeline([("scale", StandardScaler()), ("model", estimator)])
    raise ValueError(f"unsupported model_name: {model_name}")


def _fit_logistic_madl(
    features: pd.DataFrame,
    labels: pd.Series,
    forward_returns: pd.Series,
    cfg: DirectionalForexMLConfig,
) -> tuple[Any, float]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    candidate_c = (0.01, 0.1, 1.0, 10.0)
    splitter = TimeSeriesSplit(n_splits=min(cfg.cv_splits, max(2, len(features) // 20)))
    best_c = candidate_c[0]
    best_score = -np.inf
    for c_value in candidate_c:
        scores: list[float] = []
        for train_idx, test_idx in splitter.split(features):
            model = Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(C=c_value, max_iter=cfg.max_iter, solver="lbfgs", random_state=cfg.random_state),
                    ),
                ]
            )
            model.fit(features.iloc[train_idx], labels.iloc[train_idx])
            prediction = model.predict(features.iloc[test_idx])
            scores.append(madl_score(labels.iloc[test_idx], prediction, forward_returns.iloc[test_idx]))
        score = float(np.mean(scores))
        if score > best_score:
            best_c = c_value
            best_score = score

    final_model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(C=best_c, max_iter=cfg.max_iter, solver="lbfgs", random_state=cfg.random_state),
            ),
        ]
    )
    final_model.fit(features, labels)
    return final_model, best_score


def _fit_randomized_search(
    model: Any,
    features: pd.DataFrame,
    labels: pd.Series,
    cfg: DirectionalForexMLConfig,
) -> tuple[Any, float | None]:
    from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

    params = _param_distributions(cfg.model_name)
    if not params:
        model.fit(features, labels)
        return model, None
    splitter = TimeSeriesSplit(n_splits=min(cfg.cv_splits, max(2, len(features) // 20)))
    search = RandomizedSearchCV(
        estimator=model,
        param_distributions=params,
        n_iter=cfg.random_search_iterations,
        scoring="accuracy",
        cv=splitter,
        random_state=cfg.random_state,
        n_jobs=1,
        error_score="raise",
    )
    search.fit(features, labels)
    return search.best_estimator_, float(search.best_score_)


def _param_distributions(model_name: ModelName) -> dict[str, list[Any]]:
    if model_name == "logistic":
        return {
            "model__C": [0.01, 0.1, 1.0, 10.0],
            "model__penalty": ["l2"],
        }
    if model_name == "decision_tree":
        return {
            "max_depth": [2, 3, 4, 5, 7],
            "min_samples_leaf": [5, 10, 20],
            "criterion": ["gini", "entropy"],
        }
    if model_name == "random_forest":
        return {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7, None],
            "min_samples_leaf": [5, 10, 20],
            "max_features": ["sqrt", "log2", None],
        }
    if model_name == "gradient_boosting":
        return {
            "n_estimators": [50, 100, 200],
            "learning_rate": [0.02, 0.05, 0.1],
            "max_depth": [1, 2, 3],
            "subsample": [0.7, 0.85, 1.0],
        }
    if model_name == "adaboost":
        return {
            "n_estimators": [50, 100, 200],
            "learning_rate": [0.02, 0.05, 0.1, 0.2],
        }
    if model_name == "xgboost":
        return {
            "n_estimators": [50, 100, 200],
            "max_depth": [2, 3, 4],
            "learning_rate": [0.02, 0.05, 0.1],
            "subsample": [0.7, 0.85, 1.0],
            "colsample_bytree": [0.7, 0.85, 1.0],
        }
    if model_name == "mlp":
        return {
            "model__hidden_layer_sizes": [(8,), (16,), (16, 8)],
            "model__alpha": [0.0001, 0.001, 0.01],
            "model__learning_rate_init": [0.001, 0.005, 0.01],
        }
    return {}


def _predict_model_probabilities(model: Any, features: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]
    if hasattr(model, "decision_function"):
        raw = model.decision_function(features)
        return 1.0 / (1.0 + np.exp(-raw))
    return model.predict(features).astype(float)
