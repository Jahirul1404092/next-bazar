# -*- coding: utf-8 -*-
"""
Price Prediction Models for Next Bazar commodities.

Models implemented:
1. XGBoost (tabular features — primary model)
2. LightGBM (tabular features — fast alternative)
3. Prophet (time-series native — good for seasonality)
4. ARIMA/SARIMAX (classical time-series baseline)
5. Ensemble (weighted average of best models)

Evaluation:
- Walk-forward validation (expanding window)
- Metrics: MAE, RMSE, MAPE, directional accuracy

Author: Jahirul (2026)
"""

import os
import re
import sys
import json
import logging
import warnings
import argparse
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
import joblib
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    mean_absolute_percentage_error,
)
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
FEATURES_DIR = DATA_DIR / "features"
MODELS_DIR = PROJECT_DIR / "models"
OUTPUTS_DIR = PROJECT_DIR / "outputs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature columns (must match process_data.py output)
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    "price_lag_1", "price_lag_2", "price_lag_3",
    "price_lag_7", "price_lag_14", "price_lag_30",
    "price_rolling_mean_7", "price_rolling_mean_14",
    "price_rolling_mean_30", "price_rolling_mean_60",
    "price_rolling_std_7", "price_rolling_std_14",
    "price_rolling_std_30", "price_rolling_std_60",
    "price_rolling_min_7", "price_rolling_max_7",
    "price_rolling_min_30", "price_rolling_max_30",
    "price_diff_1", "price_diff_7", "price_diff_30",
    "price_pct_change_1", "price_pct_change_7", "price_pct_change_30",
    "price_accel",
    "day_of_week", "day_of_month", "month", "year",
    "week_of_year", "is_weekend", "quarter",
    "price_spread", "price_spread_pct",
    "volatility_7", "volatility_30", "trend_30",
]

TARGET = "price"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute regression and directional accuracy metrics."""
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_t, y_p = y_true[mask], y_pred[mask]

    if len(y_t) == 0:
        return {"mae": np.nan, "rmse": np.nan, "mape": np.nan, "dir_acc": np.nan}

    mae = mean_absolute_error(y_t, y_p)
    rmse = np.sqrt(mean_squared_error(y_t, y_p))

    # MAPE (avoid division by zero)
    nonzero = y_t != 0
    if nonzero.sum() > 0:
        mape = mean_absolute_percentage_error(y_t[nonzero], y_p[nonzero]) * 100
    else:
        mape = np.nan

    # Directional accuracy: did we predict the direction of change?
    if len(y_t) > 1:
        true_dir = np.diff(y_t) > 0
        pred_dir = np.diff(y_p) > 0
        dir_acc = np.mean(true_dir == pred_dir) * 100
    else:
        dir_acc = np.nan

    return {"mae": mae, "rmse": rmse, "mape": mape, "dir_acc": dir_acc}


# ---------------------------------------------------------------------------
# Model classes
# ---------------------------------------------------------------------------

class XGBModel:
    """XGBoost regressor for price prediction."""

    def __init__(self, params=None):
        from xgboost import XGBRegressor
        default_params = {
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "n_jobs": -1,
            "verbosity": 0,
        }
        if params:
            default_params.update(params)
        self.model = XGBRegressor(**default_params)
        self.name = "XGBoost"

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        fit_params = {}
        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["verbose"] = False
        self.model.fit(X_train, y_train, **fit_params)

    def predict(self, X):
        return self.model.predict(X)

    def feature_importance(self):
        return dict(zip(FEATURE_COLS, self.model.feature_importances_))

    def save(self, path):
        joblib.dump(self.model, path)

    def load(self, path):
        self.model = joblib.load(path)


class LGBModel:
    """LightGBM regressor for price prediction."""

    def __init__(self, params=None):
        from lightgbm import LGBMRegressor
        default_params = {
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 10,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }
        if params:
            default_params.update(params)
        self.model = LGBMRegressor(**default_params)
        self.name = "LightGBM"

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        fit_params = {}
        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["callbacks"] = [lambda env: None]  # suppress output
        self.model.fit(X_train, y_train, **fit_params)

    def predict(self, X):
        return self.model.predict(X)

    def feature_importance(self):
        return dict(zip(FEATURE_COLS, self.model.feature_importances_))

    def save(self, path):
        joblib.dump(self.model, path)

    def load(self, path):
        self.model = joblib.load(path)


class ProphetModel:
    """Facebook Prophet for time-series forecasting."""

    def __init__(self):
        self.model = None
        self.name = "Prophet"

    def fit(self, df_train: pd.DataFrame):
        """df_train must have columns: ds (date), y (price)."""
        from prophet import Prophet
        self.model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.1,
            seasonality_prior_scale=10.0,
        )
        self.model.fit(df_train[["ds", "y"]])

    def predict(self, df_future: pd.DataFrame) -> np.ndarray:
        forecast = self.model.predict(df_future[["ds"]])
        return forecast["yhat"].values

    def save(self, path):
        joblib.dump(self.model, path)

    def load(self, path):
        self.model = joblib.load(path)


class SARIMAXModel:
    """SARIMAX for classical time-series forecasting."""

    def __init__(self, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model_fit = None
        self.name = "SARIMAX"

    def fit(self, series: pd.Series):
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        model = SARIMAX(
            series,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        self.model_fit = model.fit(disp=False, maxiter=200)

    def predict(self, steps: int) -> np.ndarray:
        forecast = self.model_fit.forecast(steps=steps)
        return forecast.values

    def save(self, path):
        joblib.dump(self.model_fit, path)

    def load(self, path):
        self.model_fit = joblib.load(path)


# ---------------------------------------------------------------------------
# Training & Evaluation
# ---------------------------------------------------------------------------

def prepare_data(df: pd.DataFrame) -> tuple:
    """Prepare features and target from the feature-engineered dataframe."""
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)

    # Select available feature columns
    available_features = [c for c in FEATURE_COLS if c in df.columns]
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        logger.warning(f"Missing features: {missing}")

    X = df[available_features].copy()
    y = df[TARGET].copy()

    # Drop rows with NaN in features or target
    valid = X.notna().all(axis=1) & y.notna()
    X = X[valid]
    y = y[valid]
    dates = df.loc[valid, "date"]

    return X, y, dates, available_features


def walk_forward_validate(
    df: pd.DataFrame,
    model_class,
    n_splits: int = 5,
    test_size: int = 30,  # days
) -> dict:
    """
    Walk-forward validation: train on expanding window, test on next test_size days.
    """
    X, y, dates, features = prepare_data(df)

    if len(X) < 100:
        return {"error": "Insufficient data", "n_samples": len(X)}

    # Create time-based splits
    tscv = TimeSeriesSplit(n_splits=n_splits, test_size=test_size)

    all_metrics = []
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model = model_class()
        model.fit(X_train.values, y_train.values,
                  X_val=X_test.values, y_val=y_test.values)

        y_pred = model.predict(X_test.values)
        metrics = compute_metrics(y_test.values, y_pred)
        metrics["fold"] = fold
        all_metrics.append(metrics)

    avg_metrics = {
        "mae": np.mean([m["mae"] for m in all_metrics]),
        "rmse": np.mean([m["rmse"] for m in all_metrics]),
        "mape": np.mean([m["mape"] for m in all_metrics]),
        "dir_acc": np.mean([m["dir_acc"] for m in all_metrics]),
        "n_folds": n_splits,
        "n_samples": len(X),
    }

    return avg_metrics


def train_final_model(
    df: pd.DataFrame,
    model_class,
    commodity_name: str,
) -> tuple:
    """Train final model on all data and return model + metrics."""
    X, y, dates, features = prepare_data(df)

    if len(X) < 50:
        return None, {"error": "Insufficient data"}

    # Use last 30 days as holdout
    split_idx = len(X) - 30
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    model = model_class()
    model.fit(X_train.values, y_train.values,
              X_val=X_test.values, y_val=y_test.values)

    # Evaluate on holdout
    y_pred = model.predict(X_test.values)
    metrics = compute_metrics(y_test.values, y_pred)

    # Retrain on ALL data for production
    model_final = model_class()
    model_final.fit(X.values, y.values)

    return model_final, metrics


def forecast_future(
    df: pd.DataFrame,
    model,
    days_ahead: int = 30,
) -> pd.DataFrame:
    """
    Generate future predictions by iteratively forecasting one day at a time.
    Uses the previous prediction as input for the next step.
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    available_features = [c for c in FEATURE_COLS if c in df.columns]

    last_row = df.iloc[-1].copy()
    last_date = pd.to_datetime(last_row["date"])
    last_price = last_row["price"]

    predictions = []

    for i in range(1, days_ahead + 1):
        future_date = last_date + timedelta(days=i)

        # Build feature row from the latest state
        feat = {}

        # Lag features — shift based on predictions
        all_prices = list(df["price"].values) + [p["predicted_price"] for p in predictions]

        for lag in [1, 2, 3, 7, 14, 30]:
            idx = len(all_prices) - lag
            feat[f"price_lag_{lag}"] = all_prices[idx] if idx >= 0 else np.nan

        # Rolling stats from recent prices
        for window in [7, 14, 30, 60]:
            recent = all_prices[-window:] if len(all_prices) >= window else all_prices
            feat[f"price_rolling_mean_{window}"] = np.mean(recent)
            feat[f"price_rolling_std_{window}"] = np.std(recent) if len(recent) > 1 else 0
            feat[f"price_rolling_min_{window}"] = np.min(recent)
            feat[f"price_rolling_max_{window}"] = np.max(recent)

        # Price changes
        if len(all_prices) >= 2:
            feat["price_diff_1"] = all_prices[-1] - all_prices[-2]
        else:
            feat["price_diff_1"] = 0
        feat["price_diff_7"] = all_prices[-1] - all_prices[-8] if len(all_prices) >= 8 else 0
        feat["price_diff_30"] = all_prices[-1] - all_prices[-31] if len(all_prices) >= 31 else 0

        if all_prices[-2] != 0 and len(all_prices) >= 2:
            feat["price_pct_change_1"] = (all_prices[-1] - all_prices[-2]) / all_prices[-2]
        else:
            feat["price_pct_change_1"] = 0
        feat["price_pct_change_7"] = 0  # simplified
        feat["price_pct_change_30"] = 0

        feat["price_accel"] = 0  # simplified for future

        # Calendar
        feat["day_of_week"] = future_date.weekday()
        feat["day_of_month"] = future_date.day
        feat["month"] = future_date.month
        feat["year"] = future_date.year
        feat["week_of_year"] = future_date.isocalendar()[1]
        feat["is_weekend"] = 1 if future_date.weekday() >= 5 else 0
        feat["quarter"] = (future_date.month - 1) // 3 + 1

        # TCB spread (use last known)
        feat["price_spread"] = last_row.get("price_spread", 0)
        feat["price_spread_pct"] = last_row.get("price_spread_pct", 0)

        # Volatility and trend (use last known)
        feat["volatility_7"] = last_row.get("volatility_7", 0)
        feat["volatility_30"] = last_row.get("volatility_30", 0)
        feat["trend_30"] = last_row.get("trend_30", 0)

        # Build feature vector
        X_future = pd.DataFrame([feat])[available_features]
        X_future = X_future.fillna(0)

        pred = model.predict(X_future.values)[0]

        predictions.append({
            "date": future_date,
            "predicted_price": pred,
        })

    return pd.DataFrame(predictions)


# ---------------------------------------------------------------------------
# Run all commodities
# ---------------------------------------------------------------------------

def run_all_commodities(
    models_to_use: list = None,
    forecast_days: int = 30,
    n_cv_splits: int = 5,
):
    """Train models for all commodities and generate forecasts."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if models_to_use is None:
        models_to_use = ["xgboost", "lightgbm"]

    model_map = {
        "xgboost": XGBModel,
        "lightgbm": LGBModel,
    }

    # Find all commodity feature files
    feature_files = sorted(FEATURES_DIR.glob("*.csv"))
    if not feature_files:
        logger.error(f"No feature files found in {FEATURES_DIR}")
        logger.error("Run process_data.py first!")
        return

    logger.info(f"Found {len(feature_files)} commodity files")

    all_results = []
    all_forecasts = []

    for fpath in tqdm(feature_files, desc="Training models"):
        commodity_name = fpath.stem
        df = pd.read_csv(fpath, parse_dates=["date"])

        if len(df) < 60:
            logger.warning(f"Skipping {commodity_name}: only {len(df)} rows")
            continue

        for model_name in models_to_use:
            if model_name not in model_map:
                continue

            try:
                # Walk-forward CV
                cv_metrics = walk_forward_validate(
                    df, model_map[model_name], n_splits=n_cv_splits
                )

                if "error" in cv_metrics:
                    logger.warning(f"{commodity_name}/{model_name}: {cv_metrics['error']}")
                    continue

                # Train final model
                model, holdout_metrics = train_final_model(
                    df, model_map[model_name], commodity_name
                )

                if model is None:
                    continue

                # Save model
                model_path = MODELS_DIR / f"{commodity_name}_{model_name}.pkl"
                model.save(model_path)

                # Generate forecast
                forecast = forecast_future(df, model, days_ahead=forecast_days)
                forecast["commodity"] = commodity_name
                forecast["model"] = model_name
                all_forecasts.append(forecast)

                # Feature importance
                importance = model.feature_importance()
                top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]

                result = {
                    "commodity": commodity_name,
                    "model": model_name,
                    "n_samples": len(df),
                    "cv_mae": cv_metrics["mae"],
                    "cv_rmse": cv_metrics["rmse"],
                    "cv_mape": cv_metrics["mape"],
                    "cv_dir_acc": cv_metrics["dir_acc"],
                    "holdout_mae": holdout_metrics["mae"],
                    "holdout_rmse": holdout_metrics["rmse"],
                    "holdout_mape": holdout_metrics["mape"],
                    "holdout_dir_acc": holdout_metrics["dir_acc"],
                    "top_features": str(top_features),
                }
                all_results.append(result)

                logger.info(
                    f"{commodity_name} | {model_name} | "
                    f"CV MAE={cv_metrics['mae']:.2f} | "
                    f"Holdout MAE={holdout_metrics['mae']:.2f} | "
                    f"Dir Acc={holdout_metrics['dir_acc']:.1f}%"
                )

            except Exception as e:
                logger.error(f"Error training {commodity_name}/{model_name}: {e}")

    # Save results summary
    if all_results:
        results_df = pd.DataFrame(all_results)
        results_path = OUTPUTS_DIR / "model_results.csv"
        results_df.to_csv(results_path, index=False, encoding="utf-8-sig")
        logger.info(f"\nResults saved to {results_path}")

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("MODEL PERFORMANCE SUMMARY")
        logger.info("=" * 80)
        for model_name in models_to_use:
            subset = results_df[results_df["model"] == model_name]
            if len(subset) > 0:
                logger.info(f"\n{model_name.upper()}:")
                logger.info(f"  Avg CV MAE:       {subset['cv_mae'].mean():.2f}")
                logger.info(f"  Avg CV RMSE:      {subset['cv_rmse'].mean():.2f}")
                logger.info(f"  Avg CV MAPE:      {subset['cv_mape'].mean():.1f}%")
                logger.info(f"  Avg Dir Accuracy: {subset['cv_dir_acc'].mean():.1f}%")

    # Save forecasts
    if all_forecasts:
        forecasts_df = pd.concat(all_forecasts, ignore_index=True)
        forecast_path = OUTPUTS_DIR / "forecasts.csv"
        forecasts_df.to_csv(forecast_path, index=False, encoding="utf-8-sig")
        logger.info(f"\nForecasts saved to {forecast_path}")

    # Also train Prophet on top commodities
    logger.info("\n" + "=" * 60)
    logger.info("Training Prophet models on top commodities...")
    _train_prophet_models(feature_files, forecast_days)


def _train_prophet_models(feature_files: list, forecast_days: int):
    """Train Prophet models on commodities that have enough data."""
    try:
        from prophet import Prophet
    except ImportError:
        logger.warning("Prophet not installed. Skipping Prophet models.")
        logger.warning("Install with: pip install prophet")
        return

    prophet_results = []
    prophet_forecasts = []

    for fpath in tqdm(feature_files[:20], desc="Prophet models"):  # top 20 only
        commodity_name = fpath.stem
        df = pd.read_csv(fpath, parse_dates=["date"])

        if len(df) < 100:
            continue

        try:
            # Prepare Prophet format
            prophet_df = df[["date", "price"]].rename(columns={"date": "ds", "price": "y"})
            prophet_df = prophet_df.dropna()

            # Split
            split_idx = len(prophet_df) - 30
            train = prophet_df.iloc[:split_idx]
            test = prophet_df.iloc[split_idx:]

            model = ProphetModel()
            model.fit(train)

            # Evaluate
            y_pred = model.predict(test)
            metrics = compute_metrics(test["y"].values, y_pred)

            # Forecast future
            future_dates = pd.DataFrame({
                "ds": pd.date_range(
                    prophet_df["ds"].max() + timedelta(days=1),
                    periods=forecast_days,
                    freq="D"
                )
            })
            future_pred = model.predict(future_dates)

            forecast = pd.DataFrame({
                "date": future_dates["ds"],
                "predicted_price": future_pred,
                "commodity": commodity_name,
                "model": "prophet",
            })
            prophet_forecasts.append(forecast)

            # Save model
            model_path = MODELS_DIR / f"{commodity_name}_prophet.pkl"
            model.save(model_path)

            prophet_results.append({
                "commodity": commodity_name,
                "model": "prophet",
                "holdout_mae": metrics["mae"],
                "holdout_mape": metrics["mape"],
                "holdout_dir_acc": metrics["dir_acc"],
            })

            logger.info(
                f"Prophet | {commodity_name} | "
                f"MAE={metrics['mae']:.2f} | MAPE={metrics['mape']:.1f}%"
            )

        except Exception as e:
            logger.warning(f"Prophet failed for {commodity_name}: {e}")

    if prophet_results:
        pd.DataFrame(prophet_results).to_csv(
            OUTPUTS_DIR / "prophet_results.csv", index=False
        )
    if prophet_forecasts:
        pd.concat(prophet_forecasts).to_csv(
            OUTPUTS_DIR / "prophet_forecasts.csv", index=False
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train price prediction models")
    parser.add_argument(
        "--models", nargs="+", default=["xgboost", "lightgbm"],
        choices=["xgboost", "lightgbm", "prophet", "sarimax"],
        help="Models to train"
    )
    parser.add_argument(
        "--forecast-days", type=int, default=30,
        help="Number of days to forecast into the future"
    )
    parser.add_argument(
        "--cv-splits", type=int, default=5,
        help="Number of walk-forward CV splits"
    )
    parser.add_argument(
        "--commodity", type=str, default=None,
        help="Train only for a specific commodity (filename stem)"
    )
    args = parser.parse_args()

    if args.commodity:
        fpath = FEATURES_DIR / f"{args.commodity}.csv"
        if not fpath.exists():
            logger.error(f"Commodity file not found: {fpath}")
            return
        # Train single commodity
        df = pd.read_csv(fpath, parse_dates=["date"])
        logger.info(f"Training for: {args.commodity} ({len(df)} rows)")

        for model_name in args.models:
            if model_name == "xgboost":
                model, metrics = train_final_model(df, XGBModel, args.commodity)
            elif model_name == "lightgbm":
                model, metrics = train_final_model(df, LGBModel, args.commodity)

            if model:
                logger.info(f"{model_name}: {metrics}")
                forecast = forecast_future(df, model, args.forecast_days)
                print(f"\n{model_name} forecast for {args.commodity}:")
                print(forecast.to_string())
    else:
        run_all_commodities(
            models_to_use=args.models,
            forecast_days=args.forecast_days,
            n_cv_splits=args.cv_splits,
        )


if __name__ == "__main__":
    main()
