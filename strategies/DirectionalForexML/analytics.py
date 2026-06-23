"""Portfolio analytics for Directional Forex ML outputs."""

from __future__ import annotations

import numpy as np
import pandas as pd


def drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return (equity - peak) / peak


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float | None:
    clean = returns.dropna()
    if clean.empty:
        return None
    return float(-np.percentile(clean, (1 - confidence) * 100))


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float | None:
    clean = returns.dropna()
    if clean.empty:
        return None
    var = historical_var(clean, confidence)
    if var is None:
        return None
    tail = clean[clean <= -var]
    return None if tail.empty else float(-tail.mean())


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float | None:
    clean = returns.dropna()
    if clean.empty:
        return None
    excess = clean - threshold
    gains = excess[excess > 0].sum()
    losses = abs(excess[excess <= 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return float(gains / losses)


def time_underwater(equity: pd.Series) -> int:
    dd = drawdown_series(equity)
    underwater = dd < 0
    groups = (~underwater).cumsum()
    periods = underwater.groupby(groups).sum()
    return int(periods.max()) if len(periods) else 0


def calmar_ratio(equity: pd.Series) -> float | None:
    if len(equity) < 2:
        return None
    days = max((equity.index[-1] - equity.index[0]).days, 1)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (365.25 / days) - 1.0
    mdd = abs(float(drawdown_series(equity).min()))
    if mdd == 0:
        return float("inf") if cagr > 0 else 0.0
    return float(cagr / mdd)


def trade_statistics(trades: pd.DataFrame) -> dict[str, float | int | None]:
    if trades.empty or "return_pct" not in trades.columns:
        return {
            "trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "avg_win_pct": None,
            "avg_loss_pct": None,
        }
    pnl = trades["return_pct"].astype(float) / 100.0
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    return {
        "trade_count": int(len(pnl)),
        "win_rate": float(len(wins) / len(pnl)) if len(pnl) else None,
        "profit_factor": None if gross_loss == 0 else gross_profit / gross_loss,
        "expectancy": float(pnl.mean()) if len(pnl) else None,
        "avg_win_pct": float(wins.mean() * 100.0) if len(wins) else None,
        "avg_loss_pct": float(losses.mean() * 100.0) if len(losses) else None,
    }


def performance_metrics(
    returns: pd.Series,
    equity: pd.Series,
    trades: pd.DataFrame,
    *,
    initial_cash: float,
    annualization: int = 252,
) -> dict[str, float | int | None]:
    if returns.empty:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "calmar_ratio": None,
            "omega_ratio": None,
            "var_95": None,
            "cvar_95": None,
            "max_drawdown": 0.0,
            "time_underwater": 0,
            **trade_statistics(trades),
        }
    total_return = float(equity.iloc[-1] / initial_cash - 1.0)
    annualized_return = float((1.0 + total_return) ** (annualization / max(len(returns), 1)) - 1.0)
    annualized_volatility = float(returns.std(ddof=0) * np.sqrt(annualization))
    sharpe = None if annualized_volatility == 0 else float(returns.mean() / returns.std(ddof=0) * np.sqrt(annualization))
    downside = returns[returns < 0]
    sortino = None
    if not downside.empty and downside.std(ddof=0) > 0:
        sortino = float(returns.mean() / downside.std(ddof=0) * np.sqrt(annualization))
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar_ratio(equity),
        "omega_ratio": omega_ratio(returns),
        "var_95": historical_var(returns),
        "cvar_95": historical_cvar(returns),
        "max_drawdown": float(drawdown_series(equity).min()),
        "time_underwater": time_underwater(equity),
        **trade_statistics(trades),
    }
