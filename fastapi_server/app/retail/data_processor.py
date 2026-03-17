"""
データ処理モジュール
小売売上のトレーニングデータ・実績データ・予測データの読み込み、マージ、加工を担当

CSVカラム名 (01_create_dataset.ipynb で生成):
  - year_month: 日付 (YYYY-MM-DD)
  - store_type: 業態名 (百貨店, スーパー, コンビニ, ドラッグストア, EC)
  - sales_billion_yen: 売上高 (億円)
"""

import io
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
import numpy as np
import pandas as pd  # type: ignore

from app.retail.utils import json_safe_float


class RetailDataProcessor:
    def __init__(self):
        # データディレクトリはプロジェクトルートの data/ を参照
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        self.base_path = os.path.join(project_root, "data")
        self.training_data: Optional[pd.DataFrame] = None
        self.actuals_data: Optional[pd.DataFrame] = None
        self.prediction_data: Optional[pd.DataFrame] = None
        self.merged_data: Optional[pd.DataFrame] = None
        self.data_source: Optional[str] = None
        self.pct_error_denom_epsilon: float = float(
            os.getenv("PCT_ERROR_DENOM_EPSILON", "1e-6")
        )
        self._load_data()

    # ------------------------------------------------------------------
    # DataRobot Prediction API
    # ------------------------------------------------------------------

    def _build_scoring_data(self) -> pd.DataFrame:
        """学習データから予測用スコアリングデータを構築する。
        直近12ヶ月の実績 + 未来3ヶ月の空行（target=NaN）。
        AI Catalog のCSVは NaN行が欠落する場合があるため、動的に生成する。
        """
        forecast_months = int(os.getenv("FORECAST_WINDOW_END", "3"))

        if self.training_data is None or self.training_data.empty:
            raise RuntimeError("学習データが読み込まれていません")

        max_date = self.training_data["year_month"].max()
        cutoff = max_date - pd.DateOffset(months=11)
        recent = self.training_data[self.training_data["year_month"] >= cutoff].copy()

        # 未来行を追加 (target列は NaN)
        future_rows = []
        for store_type in self.training_data["store_type"].unique():
            for i in range(1, forecast_months + 1):
                future_date = max_date + pd.DateOffset(months=i)
                row: dict = {"year_month": future_date, "store_type": store_type}
                for col in recent.columns:
                    if col not in ("year_month", "store_type"):
                        row[col] = np.nan
                future_rows.append(row)

        scoring_df = pd.concat([recent, pd.DataFrame(future_rows)], ignore_index=True)
        scoring_df = scoring_df.sort_values(["store_type", "year_month"]).reset_index(drop=True)
        print(f"スコアリングデータ構築: {len(recent)} 実績行 + {len(future_rows)} 未来行 = {len(scoring_df)} 行")
        return scoring_df

    def _fetch_predictions_from_api(self) -> pd.DataFrame:
        endpoint = os.getenv("DATAROBOT_ENDPOINT", "").rstrip("/")
        token = os.getenv("DATAROBOT_API_TOKEN", "")
        deployment_id = os.getenv("FORECAST_DEPLOYMENT_ID", "")

        if not all([endpoint, token, deployment_id]):
            raise RuntimeError("予測 API に必要な環境変数が不足しています")

        base = endpoint.rstrip("/")
        if base.endswith("/api/v2"):
            base = base[: -len("/api/v2")]
        predict_url = f"{base}/api/v2/deployments/{deployment_id}/predictions"

        # Step 1: スコアリングデータを動的に構築 (NaN行を確実に含める)
        scoring_df = self._build_scoring_data()
        scoring_csv_bytes = scoring_df.to_csv(index=False).encode("utf-8")
        print(f"Prediction API に {len(scoring_df)} 行を送信: {predict_url}")

        # Step 2: Prediction API にCSVデータを送信
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "text/csv; encoding=utf-8",
            "Accept": "text/csv",
        }

        with httpx.Client(follow_redirects=True, timeout=180.0) as client:
            resp = client.post(predict_url, content=scoring_csv_bytes, headers=headers)
            if resp.status_code != 200:
                print(f"Prediction API エラー ({resp.status_code}): {resp.text[:1000]}")
            resp.raise_for_status()
            pred_df = pd.read_csv(io.BytesIO(resp.content))

        print(f"Prediction API 成功: {len(pred_df)} 行, カラム: {list(pred_df.columns)}")

        # キャッシュとして保存
        cache_path = os.path.join(self.base_path, "predictions_dataset.csv")
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            pred_df.to_csv(cache_path, index=False)
            print(f"予測キャッシュ保存: {cache_path}")
        except Exception:
            pass

        return pred_df

    def _download_ai_catalog_csv(self, dataset_id: str) -> pd.DataFrame:
        endpoint = os.getenv("DATAROBOT_ENDPOINT", "").rstrip("/")
        token = os.getenv("DATAROBOT_API_TOKEN", "")
        if not endpoint or not token:
            raise RuntimeError("DATAROBOT_ENDPOINT or DATAROBOT_API_TOKEN が未設定")

        url = f"{endpoint}/datasets/{dataset_id}/file"
        headers = {"Authorization": f"Token {token}", "x-datarobot-api-token": token}
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return pd.read_csv(io.BytesIO(resp.content))

    # ------------------------------------------------------------------
    # データ読み込み
    # ------------------------------------------------------------------

    def _load_data(self):
        try:
            data_source = (os.getenv("RETAIL_DATA_SOURCE") or "local").strip().lower()

            # ローカル CSV パス (01_create_dataset.ipynb の出力名に準拠)
            training_path = os.path.join(self.base_path, "retail_sales_dataset.csv")
            actuals_path = os.path.join(self.base_path, "retail_sales_actuals.csv")
            predictions_path = os.path.join(self.base_path, "predictions_dataset.csv")

            local_exists = os.path.exists(training_path) and os.path.exists(actuals_path)

            if data_source != "ai_catalog" and local_exists:
                self.training_data = pd.read_csv(training_path)
                self.actuals_data = pd.read_csv(actuals_path)
                self.data_source = "local"
            else:
                try:
                    training_dataset_id = os.getenv("RETAIL_TRAINING_DATASET_ID", "")
                    actuals_dataset_id = os.getenv(
                        "RETAIL_ACTUALS_DATASET_ID",
                        os.getenv("ACTUALS_DATASET_ID", ""),
                    )
                    if not (training_dataset_id and actuals_dataset_id):
                        raise RuntimeError("AI Catalog データセット ID が未設定です")
                    self.training_data = self._download_ai_catalog_csv(training_dataset_id)
                    self.actuals_data = self._download_ai_catalog_csv(actuals_dataset_id)
                    self.data_source = "ai_catalog"
                except Exception as ai_err:
                    if local_exists:
                        print(f"AI Catalog 読み込み失敗 ({ai_err}); ローカルにフォールバック")
                        self.training_data = pd.read_csv(training_path)
                        self.actuals_data = pd.read_csv(actuals_path)
                        self.data_source = "local"
                    else:
                        raise FileNotFoundError(
                            f"ローカル CSV ({self.base_path}) も AI Catalog も利用不可"
                        ) from ai_err

            # 日付列のパース — カラム名 year_month (予測API呼び出し前に実行)
            for df in [self.training_data, self.actuals_data]:
                if "year_month" in df.columns:
                    df["year_month"] = pd.to_datetime(df["year_month"])
                elif "date" in df.columns:
                    df.rename(columns={"date": "year_month"}, inplace=True)
                    df["year_month"] = pd.to_datetime(df["year_month"])

            # 予測データ: API → ローカルフォールバック
            try:
                self.prediction_data = self._fetch_predictions_from_api()
                print("予測データを DataRobot Prediction API から取得しました")
            except Exception as api_err:
                print(f"Prediction API 失敗 ({api_err}); ローカルにフォールバック")
                if os.path.exists(predictions_path):
                    self.prediction_data = pd.read_csv(predictions_path)
                else:
                    print("警告: 予測データなし。実績のみで動作します。")
                    self.prediction_data = pd.DataFrame()

            if not self.prediction_data.empty:
                if "year_month" in self.prediction_data.columns:
                    self.prediction_data["year_month"] = pd.to_datetime(self.prediction_data["year_month"])
                elif "date" in self.prediction_data.columns:
                    self.prediction_data.rename(columns={"date": "year_month"}, inplace=True)
                    self.prediction_data["year_month"] = pd.to_datetime(self.prediction_data["year_month"])

            self._merge_data()
            print(f"データ読み込み完了 ({self.data_source}): {len(self.merged_data)} レコード")

        except Exception as e:
            print(f"データ読み込みエラー: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # データマージ
    # ------------------------------------------------------------------

    def _merge_data(self):
        try:
            all_actuals = pd.concat(
                [self.training_data, self.actuals_data], ignore_index=True
            )

            # 予測カラム名の自動検出
            pred_col = None
            if not self.prediction_data.empty:
                for candidate in [
                    "sales_billion_yen_PREDICTION",
                    "sales_billion_yen (actual)_PREDICTION",
                    "sales_billion_yen_prediction",
                    "sales_amount_PREDICTION",
                ]:
                    if candidate in self.prediction_data.columns:
                        pred_col = candidate
                        break

            if pred_col:
                pred_subset = self.prediction_data.copy()
                pred_subset.rename(columns={pred_col: "predicted_sales"}, inplace=True)

                keep_cols = ["year_month", "store_type", "predicted_sales"]
                for col in ["PREDICTION_90_PERCENTILE_LOW", "PREDICTION_90_PERCENTILE_HIGH"]:
                    if col in pred_subset.columns:
                        keep_cols.append(col)
                pred_subset = pred_subset[[c for c in keep_cols if c in pred_subset.columns]]

                print(f"予測データ: {len(self.prediction_data)} -> {len(pred_subset)} レコード")

                self.merged_data = pd.merge(
                    all_actuals, pred_subset,
                    on=["store_type", "year_month"], how="left",
                )
            else:
                self.merged_data = all_actuals.copy()
                self.merged_data["predicted_sales"] = np.nan

            print(f"マージ後データ形状: {self.merged_data.shape}")
            pred_count = self.merged_data["predicted_sales"].notna().sum()
            print(f"予測あり: {pred_count} / {len(self.merged_data)} レコード")

            # 予測誤差
            self.merged_data["forecast_error"] = (
                self.merged_data["sales_billion_yen"] - self.merged_data["predicted_sales"]
            )
            self.merged_data["abs_error"] = np.abs(self.merged_data["forecast_error"])

            denom = self.merged_data["sales_billion_yen"].astype(float)
            num = self.merged_data["forecast_error"].astype(float)
            valid = np.isfinite(denom) & (np.abs(denom) > self.pct_error_denom_epsilon)
            self.merged_data["pct_error"] = np.where(valid, (num / denom) * 100, np.nan)

            self.merged_data["date_only"] = self.merged_data["year_month"].dt.date
            self.merged_data["month"] = self.merged_data["year_month"].dt.month
            self.merged_data["year"] = self.merged_data["year_month"].dt.year

        except Exception as e:
            print(f"データマージエラー: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # 公開メソッド
    # ------------------------------------------------------------------

    def get_merged_data(self) -> pd.DataFrame:
        return self.merged_data.copy()

    def get_forecast_data(
        self,
        store_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = 1000,
    ) -> List[Dict[str, Any]]:
        data = self.merged_data.copy()

        if store_type:
            data = data[data["store_type"] == store_type]
        if start_date:
            data = data[data["date_only"] >= start_date]
        if end_date:
            data = data[data["date_only"] <= end_date]

        data = data.sort_values("year_month")
        if limit:
            data = data.head(limit)

        result = []
        for _, row in data.iterrows():
            record = {
                "date": row["year_month"].isoformat() if hasattr(row["year_month"], "isoformat") else str(row["year_month"]),
                "store_type": row["store_type"],
                "actual_sales": json_safe_float(row["sales_billion_yen"]),
                "predicted_sales": json_safe_float(row.get("predicted_sales")),
                "error": json_safe_float(row.get("forecast_error")),
                "abs_error": json_safe_float(row.get("abs_error")),
                "pct_error": json_safe_float(row.get("pct_error")),
                "confidence_low": json_safe_float(row.get("PREDICTION_90_PERCENTILE_LOW")),
                "confidence_high": json_safe_float(row.get("PREDICTION_90_PERCENTILE_HIGH")),
            }
            result.append(record)
        return result

    def get_specific_forecast(
        self, store_type: str, target_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        data = self.merged_data[
            (self.merged_data["store_type"] == store_type)
            & (self.merged_data["year_month"] == target_date)
        ]
        if data.empty:
            return None
        return data.iloc[0].to_dict()

    def get_store_types(self) -> List[str]:
        return sorted(self.merged_data["store_type"].unique().tolist())

    def get_date_range(self) -> Dict[str, str]:
        return {
            "start": self.merged_data["year_month"].min().isoformat(),
            "end": self.merged_data["year_month"].max().isoformat(),
        }
