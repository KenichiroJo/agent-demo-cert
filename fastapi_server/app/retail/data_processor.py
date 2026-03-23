"""
データ処理モジュール
小売売上のトレーニングデータ・実績データ・予測データの読み込み、マージ、加工を担当

CSVカラム名 (01_create_dataset.ipynb で生成):
  - year_month: 日付 (YYYY-MM-DD)
  - store_type: 業態名 (百貨店, スーパー, コンビニ, ドラッグストア, EC)
  - sales_billion_yen: 売上高 (億円)

Prediction API レスポンスカラム:
  - store_type, year_month, FORECAST_POINT, FORECAST_DISTANCE
  - sales_billion_yen (actual)_PREDICTION
  - DEPLOYMENT_APPROVAL_STATUS
"""

import io
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
import numpy as np
import pandas as pd  # type: ignore

from app.retail.runtime_params import get_runtime_param
from app.retail.utils import json_safe_float


class RetailDataProcessor:
    def __init__(self):
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
    # ユーティリティ
    # ------------------------------------------------------------------

    @staticmethod
    def _to_tz_naive(series: pd.Series) -> pd.Series:
        """タイムゾーン付き datetime を tz-naive (UTC相当) に統一する。
        Prediction API は UTC 付き timestamps を返す場合があり、
        training/actuals の tz-naive と merge するとエラーになるため。"""
        if hasattr(series.dt, "tz") and series.dt.tz is not None:
            return series.dt.tz_convert("UTC").dt.tz_localize(None)
        return series

    @staticmethod
    def _parse_date_column(df: pd.DataFrame) -> pd.DataFrame:
        """year_month (または date) カラムを tz-naive datetime64 に変換する。"""
        if "year_month" in df.columns:
            df["year_month"] = pd.to_datetime(df["year_month"])
        elif "date" in df.columns:
            df.rename(columns={"date": "year_month"}, inplace=True)
            df["year_month"] = pd.to_datetime(df["year_month"])
        if "year_month" in df.columns:
            df["year_month"] = RetailDataProcessor._to_tz_naive(df["year_month"])
        return df

    # ------------------------------------------------------------------
    # DataRobot Prediction API
    # ------------------------------------------------------------------

    def _fetch_predictions_from_api(self) -> pd.DataFrame:
        """ローリング forecastPoint でPrediction APIを呼び出し、全期間の予測を取得する。
        ERCOT パターン: 表示期間全体に予測線を表示するため、
        forecastPoint をずらしながら複数回APIを呼ぶ。
        結果はキャッシュし、次回起動時はキャッシュを優先する。
        """
        endpoint = get_runtime_param("DATAROBOT_ENDPOINT").rstrip("/")
        token = get_runtime_param("DATAROBOT_API_TOKEN")
        deployment_id = get_runtime_param("FORECAST_DEPLOYMENT_ID")

        if not all([endpoint, token, deployment_id]):
            raise RuntimeError("予測 API に必要な環境変数が不足しています")

        base = endpoint.rstrip("/")
        if base.endswith("/api/v2"):
            base = base[: -len("/api/v2")]
        predict_url = f"{base}/api/v2/deployments/{deployment_id}/predictions"

        # キャッシュ確認: 1日以内のキャッシュがあればそれを使う
        cache_path = os.path.join(self.base_path, "predictions_dataset.csv")
        cache_max_age = int(os.getenv("PREDICTION_CACHE_MAX_AGE_HOURS", "24"))
        if os.path.exists(cache_path):
            cache_age_hours = (
                datetime.now().timestamp() - os.path.getmtime(cache_path)
            ) / 3600
            if cache_age_hours < cache_max_age:
                print(f"予測キャッシュ使用 (経過時間: {cache_age_hours:.1f}h < {cache_max_age}h)")
                return pd.read_csv(cache_path)

        if self.training_data is None or self.training_data.empty:
            raise RuntimeError("学習データが読み込まれていません")

        forecast_window = int(os.getenv("FORECAST_WINDOW_END", "3"))
        feature_window = int(os.getenv("FEATURE_DERIVATION_WINDOW", "12"))

        # 全学習データをスコアリングコンテキストとして使用
        full_data = self.training_data.copy()
        scoring_csv_bytes = full_data.to_csv(index=False).encode("utf-8")

        # ローリング forecastPoint を生成
        all_dates = sorted(full_data["year_month"].unique())
        max_date = all_dates[-1]

        # feature_window 分の履歴を確保してから予測開始
        if len(all_dates) <= feature_window:
            start_idx = 0
        else:
            start_idx = feature_window

        forecast_points = all_dates[start_idx::forecast_window]
        # 最終日も必ず含める（未来予測のため）
        if max_date not in forecast_points:
            forecast_points = list(forecast_points) + [max_date]

        print(
            f"ローリング予測: {len(forecast_points)} 回のAPI呼び出し "
            f"(feature_window={feature_window}, forecast_window={forecast_window})"
        )

        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "text/csv; encoding=utf-8",
            "Accept": "text/csv",
        }

        all_predictions: list[pd.DataFrame] = []
        with httpx.Client(follow_redirects=True, timeout=180.0) as client:
            for fp in forecast_points:
                fp_str = pd.Timestamp(fp).strftime("%Y-%m-%dT00:00:00.000Z")
                try:
                    resp = client.post(
                        predict_url,
                        content=scoring_csv_bytes,
                        headers=headers,
                        params={"forecastPoint": fp_str},
                    )
                    if resp.status_code == 200:
                        pred_df = pd.read_csv(io.BytesIO(resp.content))
                        all_predictions.append(pred_df)
                        print(f"  forecastPoint={fp_str[:7]}: {len(pred_df)} 行")
                    else:
                        body_preview = resp.text[:300] if resp.text else "(empty)"
                        print(f"  forecastPoint={fp_str[:7]}: エラー {resp.status_code} - {body_preview}")
                except Exception as e:
                    print(f"  forecastPoint={fp_str[:7]}: 例外 {e}")

        if not all_predictions:
            raise RuntimeError("全ての予測APIコールが失敗しました")

        result = pd.concat(all_predictions, ignore_index=True)
        print(
            f"Prediction API 成功 (全体): {len(result)} 行, "
            f"カラム: {list(result.columns)}"
        )

        # FORECAST_DISTANCE で重複排除 (最短距離=最も信頼性の高い予測を採用)
        if "FORECAST_DISTANCE" in result.columns:
            before = len(result)
            result = result.sort_values("FORECAST_DISTANCE")
            result = result.drop_duplicates(
                subset=["store_type", "year_month"], keep="first"
            )
            print(f"重複排除: {before} -> {len(result)} レコード")

        # キャッシュ保存
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            result.to_csv(cache_path, index=False)
            print(f"予測キャッシュ保存: {cache_path}")
        except Exception:
            pass

        return result

    def _download_ai_catalog_csv(self, dataset_id: str) -> pd.DataFrame:
        endpoint = get_runtime_param("DATAROBOT_ENDPOINT").rstrip("/")
        token = get_runtime_param("DATAROBOT_API_TOKEN")
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
            # === 起動診断ログ ===
            print(f"[DataProcessor] base_path={self.base_path}")
            print(f"[DataProcessor] base_path exists={os.path.exists(self.base_path)}")
            _diag_keys = [
                "DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN",
                "FORECAST_DEPLOYMENT_ID", "SCORING_DATASET_ID",
                "ACTUALS_DATASET_ID", "VDB_DEPLOYMENT_ID",
            ]
            for k in _diag_keys:
                plain = os.getenv(k, "")
                mlops = os.getenv(f"MLOPS_RUNTIME_PARAM_{k}", "")
                resolved = get_runtime_param(k)
                status = "OK" if resolved else "EMPTY"
                print(f"[DataProcessor] {k}: plain={'SET' if plain else 'EMPTY'}, mlops={'SET' if mlops else 'EMPTY'}, resolved={status} ({resolved[:20]}...)" if resolved else f"[DataProcessor] {k}: plain={'SET' if plain else 'EMPTY'}, mlops={'SET' if mlops else 'EMPTY'}, resolved=EMPTY")
            # === 診断ログ終わり ===

            data_source = (os.getenv("RETAIL_DATA_SOURCE") or "local").strip().lower()

            training_path = os.path.join(self.base_path, "retail_sales_dataset.csv")
            actuals_path = os.path.join(self.base_path, "retail_sales_actuals.csv")
            predictions_path = os.path.join(self.base_path, "predictions_dataset.csv")

            local_exists = os.path.exists(training_path) and os.path.exists(actuals_path)
            print(f"[DataProcessor] local_exists={local_exists}, data_source={data_source}")

            if data_source != "ai_catalog" and local_exists:
                self.training_data = pd.read_csv(training_path)
                self.actuals_data = pd.read_csv(actuals_path)
                self.data_source = "local"
            else:
                try:
                    training_dataset_id = (
                        get_runtime_param("RETAIL_TRAINING_DATASET_ID")
                        or get_runtime_param("SCORING_DATASET_ID")
                    )
                    actuals_dataset_id = (
                        get_runtime_param("RETAIL_ACTUALS_DATASET_ID")
                        or get_runtime_param("ACTUALS_DATASET_ID")
                    )
                    if not (training_dataset_id and actuals_dataset_id):
                        raise RuntimeError("AI Catalog データセット ID が未設定です")
                    self.training_data = self._download_ai_catalog_csv(training_dataset_id)
                    print(f"[AI Catalog] training columns: {list(self.training_data.columns)}, shape: {self.training_data.shape}")
                    self.actuals_data = self._download_ai_catalog_csv(actuals_dataset_id)
                    print(f"[AI Catalog] actuals columns: {list(self.actuals_data.columns)}, shape: {self.actuals_data.shape}")
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

            # 日付パース — 予測API呼び出し前に実行 (DateOffset演算に必要)
            self.training_data = self._parse_date_column(self.training_data)
            self.actuals_data = self._parse_date_column(self.actuals_data)

            # カラム名統一: actuals の sales_amount → sales_billion_yen
            if "sales_billion_yen" not in self.actuals_data.columns and "sales_amount" in self.actuals_data.columns:
                self.actuals_data.rename(columns={"sales_amount": "sales_billion_yen"}, inplace=True)
                print("[DataProcessor] actuals カラム名変換: sales_amount → sales_billion_yen")

            # 予測データ: API → ローカルキャッシュ → フォールバック
            try:
                self.prediction_data = self._fetch_predictions_from_api()
                print("予測データを DataRobot Prediction API から取得しました")
            except Exception as api_err:
                print(f"Prediction API 失敗 ({api_err}); ローカルにフォールバック")
                if os.path.exists(predictions_path):
                    self.prediction_data = pd.read_csv(predictions_path)
                    print(f"ローカルキャッシュから予測データ読み込み: {predictions_path}")
                else:
                    print("警告: 予測データなし。実績のみで動作します。")
                    self.prediction_data = pd.DataFrame()

            # 予測データの日付パース + tz-naive 統一
            if not self.prediction_data.empty:
                self.prediction_data = self._parse_date_column(self.prediction_data)

            self._merge_data()
            print(f"データ読み込み完了 ({self.data_source}): {len(self.merged_data)} レコード")

        except Exception as e:
            print(f"データ読み込みエラー: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # データマージ (ERCOT data_processor パターンに準拠)
    # ------------------------------------------------------------------

    def _merge_data(self):
        try:
            all_actuals = pd.concat(
                [self.training_data, self.actuals_data], ignore_index=True
            )

            # カラム名の自動検出: sales_billion_yen が存在しない場合
            if "sales_billion_yen" not in all_actuals.columns:
                # 候補カラム名を探す
                sales_col = None
                for candidate in ["sales_billion_yen (actual)", "sales_amount", "sales", "value", "y"]:
                    if candidate in all_actuals.columns:
                        sales_col = candidate
                        break
                # 数値カラムで最も長い名前を使うフォールバック
                if sales_col is None:
                    numeric_cols = all_actuals.select_dtypes(include=[np.number]).columns.tolist()
                    # year_month, store_type 以外の数値カラム
                    numeric_cols = [c for c in numeric_cols if c not in ("year_month", "store_type")]
                    if numeric_cols:
                        sales_col = numeric_cols[0]

                if sales_col:
                    print(f"[DataProcessor] カラム名変換: '{sales_col}' → 'sales_billion_yen'")
                    all_actuals.rename(columns={sales_col: "sales_billion_yen"}, inplace=True)
                    # training_data と actuals_data も更新（Prediction API 用）
                    if sales_col in self.training_data.columns:
                        self.training_data.rename(columns={sales_col: "sales_billion_yen"}, inplace=True)
                    if sales_col in self.actuals_data.columns:
                        self.actuals_data.rename(columns={sales_col: "sales_billion_yen"}, inplace=True)
                else:
                    print(f"[DataProcessor] 警告: 売上カラムが見つかりません。カラム一覧: {list(all_actuals.columns)}")

            # 予測カラム名の自動検出
            pred_col = None
            if not self.prediction_data.empty:
                for candidate in [
                    "sales_billion_yen (actual)_PREDICTION",
                    "sales_billion_yen_PREDICTION",
                    "sales_billion_yen_prediction",
                    "sales_amount_PREDICTION",
                ]:
                    if candidate in self.prediction_data.columns:
                        pred_col = candidate
                        break
                # 上記に一致しない場合、_PREDICTION で終わるカラムを探す
                if pred_col is None:
                    for col in self.prediction_data.columns:
                        if col.upper().endswith("_PREDICTION"):
                            pred_col = col
                            break

            if pred_col:
                print(f"予測カラム: {pred_col}")
                pred_subset = self.prediction_data.copy()
                pred_subset.rename(columns={pred_col: "predicted_sales"}, inplace=True)

                # FORECAST_DISTANCE で重複排除 (最短距離=最新予測を採用)
                if "FORECAST_DISTANCE" in pred_subset.columns:
                    pred_subset = pred_subset.sort_values("FORECAST_DISTANCE")
                    pred_subset = pred_subset.drop_duplicates(
                        subset=["store_type", "year_month"], keep="first"
                    )
                    print(f"FORECAST_DISTANCE重複排除後: {len(pred_subset)} レコード")

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
                if not self.prediction_data.empty:
                    print(f"警告: 予測カラムが見つかりません。カラム一覧: {list(self.prediction_data.columns)}")
                self.merged_data = all_actuals.copy()
                self.merged_data["predicted_sales"] = np.nan

            print(f"マージ後データ形状: {self.merged_data.shape}")
            pred_count = self.merged_data["predicted_sales"].notna().sum()
            print(f"予測あり: {pred_count} / {len(self.merged_data)} レコード")

            # 信頼区間: API に PREDICTION_90_PERCENTILE が含まれない場合、±10%で生成
            if "PREDICTION_90_PERCENTILE_LOW" not in self.merged_data.columns:
                self.merged_data["PREDICTION_90_PERCENTILE_LOW"] = (
                    self.merged_data["predicted_sales"] * 0.90
                )
            if "PREDICTION_90_PERCENTILE_HIGH" not in self.merged_data.columns:
                self.merged_data["PREDICTION_90_PERCENTILE_HIGH"] = (
                    self.merged_data["predicted_sales"] * 1.10
                )

            # 予測誤差 (epsilon-safe) — sales_billion_yen が存在する場合のみ
            if "sales_billion_yen" in self.merged_data.columns:
                self.merged_data["forecast_error"] = (
                    self.merged_data["sales_billion_yen"] - self.merged_data["predicted_sales"]
                )
                self.merged_data["abs_error"] = np.abs(self.merged_data["forecast_error"])

                denom = self.merged_data["sales_billion_yen"].astype(float)
                num = self.merged_data["forecast_error"].astype(float)
                valid = np.isfinite(denom) & (np.abs(denom) > self.pct_error_denom_epsilon)
                self.merged_data["pct_error"] = np.where(valid, (num / denom) * 100, np.nan)
            else:
                print("[DataProcessor] 警告: sales_billion_yen カラムなし。誤差計算スキップ")
                self.merged_data["forecast_error"] = np.nan
                self.merged_data["abs_error"] = np.nan
                self.merged_data["pct_error"] = np.nan

            self.merged_data["date_only"] = self.merged_data["year_month"].dt.date
            self.merged_data["month"] = self.merged_data["year_month"].dt.month
            self.merged_data["year"] = self.merged_data["year_month"].dt.year

            # 業態名リネーム (デモ用: 全業態をEC系に統一)
            _STORE_TYPE_MAP = {
                "EC": "EC1",
                "百貨店": "EC2",
                "スーパー": "EC3",
                "コンビニ": "EC4",
                "ドラッグストア": "EC5",
            }
            self.merged_data["store_type"] = self.merged_data["store_type"].map(
                lambda x: _STORE_TYPE_MAP.get(x, x)
            )

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
