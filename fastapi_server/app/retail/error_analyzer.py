"""
誤差分析モジュール
RMSE の計算、外れ値検出、誤差コンテキストの提供を担当
"""

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional

from app.retail.utils import json_safe_float


class RetailErrorAnalyzer:
    def __init__(self):
        self.metrics_cache: Dict[str, Any] = {}

    def calculate_metrics(
        self,
        data: pd.DataFrame,
        store_type: Optional[str] = None,
        granularity: str = "monthly",
    ) -> Dict[str, Any]:
        """
        RMSE およびその他の誤差メトリクスを計算する

        パラメータ:
        - data: マージ済みの予測/実績データフレーム
        - store_type: 特定の店舗タイプで絞り込み
        - granularity: "monthly" または "yearly" の集約粒度
        """
        # 予測ありのレコードのみ
        df = data[data["predicted_sales"].notna()].copy()

        if store_type:
            df = df[df["store_type"] == store_type]

        # 二乗誤差
        df["squared_error"] = df["forecast_error"] ** 2

        if granularity == "monthly":
            # 店舗タイプ・年・月で集約
            grouped = (
                df.groupby(["store_type", "year", "month"])
                .agg(
                    {
                        "squared_error": "mean",
                        "forecast_error": "mean",
                        "abs_error": "mean",
                        "pct_error": "mean",
                        "sales_billion_yen": "mean",
                        "predicted_sales": "mean",
                    }
                )
                .reset_index()
            )
        else:  # yearly
            # 店舗タイプ・年で集約
            grouped = (
                df.groupby(["store_type", "year"])
                .agg(
                    {
                        "squared_error": "mean",
                        "forecast_error": "mean",
                        "abs_error": "mean",
                        "pct_error": "mean",
                        "sales_billion_yen": "mean",
                        "predicted_sales": "mean",
                    }
                )
                .reset_index()
            )

        # RMSE
        grouped["rmse"] = np.sqrt(grouped["squared_error"])

        # MAPE (平均絶対パーセンテージ誤差)
        grouped["mape"] = grouped["pct_error"].abs()

        # 全体統計
        overall_stats = {
            "overall_rmse": json_safe_float(np.sqrt(df["squared_error"].mean())),
            "overall_mae": json_safe_float(df["abs_error"].mean()),
            "overall_mape": json_safe_float(df["pct_error"].abs().mean()),
            "overall_bias": json_safe_float(df["forecast_error"].mean()),
            "total_records": len(df),
        }

        # 辞書形式に変換
        metrics = []
        for _, row in grouped.iterrows():
            metric = {
                "store_type": row["store_type"],
                "year": int(row["year"]),
                "rmse": json_safe_float(row["rmse"]),
                "mae": json_safe_float(row["abs_error"]),
                "mape": json_safe_float(row["mape"]),
                "bias": json_safe_float(row["forecast_error"]),
                "avg_actual": json_safe_float(row["sales_billion_yen"]),
                "avg_predicted": json_safe_float(row["predicted_sales"]),
            }

            if granularity == "monthly":
                metric["month"] = int(row["month"])

            metrics.append(metric)

        return {
            "metrics": metrics,
            "overall": overall_stats,
            "granularity": granularity,
        }

    def detect_outliers(
        self,
        data: pd.DataFrame,
        store_type: Optional[str] = None,
        threshold: float = 2.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Z スコアに基づく予測外れ値を検出する

        パラメータ:
        - data: マージ済みの予測/実績データフレーム
        - store_type: 特定の店舗タイプで絞り込み
        - threshold: 外れ値判定の標準偏差倍数
        - limit: 返却する外れ値の最大数
        """
        # 予測ありのレコードのみ
        df = data[data["predicted_sales"].notna()].copy()

        if store_type:
            df = df[df["store_type"] == store_type]

        # 店舗タイプ別の統計量を計算
        type_stats = (
            df.groupby("store_type")["abs_error"]
            .agg(["mean", "std"])
            .reset_index()
        )

        outliers = []

        for st in type_stats["store_type"].unique():
            type_data = df[df["store_type"] == st]
            type_mean = type_stats[type_stats["store_type"] == st]["mean"].values[0]
            type_std = type_stats[type_stats["store_type"] == st]["std"].values[0]

            # 外れ値の特定
            outlier_threshold = type_mean + (threshold * type_std)
            type_outliers = type_data[type_data["abs_error"] > outlier_threshold]

            # 誤差の大きい順にソート
            type_outliers = type_outliers.sort_values("abs_error", ascending=False)

            n_types = len(type_stats)
            per_type_limit = max(1, limit // n_types)

            for _, row in type_outliers.head(per_type_limit).iterrows():
                z_score = None
                if np.isfinite(type_std) and type_std != 0:
                    z_score = (row["abs_error"] - type_mean) / type_std
                outlier = {
                    "date": (
                        row["year_month"].isoformat()
                        if hasattr(row["year_month"], "isoformat")
                        else str(row["year_month"])
                    ),
                    "store_type": row["store_type"],
                    "actual_sales": json_safe_float(row["sales_billion_yen"]),
                    "predicted_sales": json_safe_float(row["predicted_sales"]),
                    "error": json_safe_float(row["forecast_error"]),
                    "abs_error": json_safe_float(row["abs_error"]),
                    "pct_error": json_safe_float(row["pct_error"]),
                    "z_score": json_safe_float(z_score),
                }
                outliers.append(outlier)

        # 全外れ値を絶対誤差の大きい順にソート
        outliers = sorted(outliers, key=lambda x: x["abs_error"] or 0, reverse=True)[
            :limit
        ]

        return outliers

    def get_error_context(
        self, data_point: Dict[str, Any], full_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        特定のデータポイントの誤差コンテキストを返す

        以下との比較統計を返す:
        - 同月の誤差
        - 同季節の誤差
        - 店舗タイプ全体の誤差
        """
        st = data_point.get("store_type")
        month = data_point.get("month")
        error = data_point.get("abs_error", 0)

        # 同じ店舗タイプでフィルタ
        type_data = full_data[
            (full_data["store_type"] == st)
            & (full_data["predicted_sales"].notna())
        ]

        context: Dict[str, Any] = {
            "point_error": error,
            "store_type_rmse": float(np.sqrt((type_data["forecast_error"] ** 2).mean())),
            "store_type_mae": float(type_data["abs_error"].mean()),
            "store_type_error_std": float(type_data["abs_error"].std()),
        }

        # 同月の統計
        if month is not None:
            month_data = type_data[type_data["month"] == month]
            if not month_data.empty:
                context["month_rmse"] = float(
                    np.sqrt((month_data["forecast_error"] ** 2).mean())
                )
                context["month_mae"] = float(month_data["abs_error"].mean())
                context["month_percentile"] = float(
                    (month_data["abs_error"] < error).mean() * 100
                )

        # 同季節の統計 (春:3-5, 夏:6-8, 秋:9-11, 冬:12-2)
        if month is not None:
            if month in [3, 4, 5]:
                season_months = [3, 4, 5]
            elif month in [6, 7, 8]:
                season_months = [6, 7, 8]
            elif month in [9, 10, 11]:
                season_months = [9, 10, 11]
            else:
                season_months = [12, 1, 2]

            season_data = type_data[type_data["month"].isin(season_months)]
            if not season_data.empty:
                context["season_rmse"] = float(
                    np.sqrt((season_data["forecast_error"] ** 2).mean())
                )
                context["season_mae"] = float(season_data["abs_error"].mean())
                context["season_percentile"] = float(
                    (season_data["abs_error"] < error).mean() * 100
                )

        # 全体パーセンタイル
        context["overall_percentile"] = float(
            (type_data["abs_error"] < error).mean() * 100
        )

        # Z スコア
        if context["store_type_error_std"] > 0:
            context["z_score"] = float(
                (error - context["store_type_mae"]) / context["store_type_error_std"]
            )

        return context
