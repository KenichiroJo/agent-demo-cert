# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Annotated

import datarobot as dr
from datarobot_genai.drmcp import dr_mcp_tool
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import ToolResult

from app.core.user_config import get_user_config

logger = logging.getLogger(__name__)


@dr_mcp_tool(tags={"forecast", "prediction", "timeseries", "retail"})
async def run_retail_forecast(
    target_month: Annotated[str, "予測対象月 (YYYY-MM形式、例: 2026-04)"],
    store_type: Annotated[
        str,
        "業態名 (百貨店/スーパー/コンビニ/ドラッグストア/EC/全体)。デフォルトは全体。",
    ] = "全体",
) -> ToolResult:
    """小売・EC売上の売上予測を実行します。

    DataRobotにデプロイされた時系列予測モデルを使用して、
    指定された月・業態の売上予測値を返します。
    過去の実績データに基づいた統計的予測です。
    """
    config = get_user_config()
    forecast_deployment_id = config.forecast_deployment_id
    scoring_dataset_id = config.scoring_dataset_id

    if not forecast_deployment_id:
        raise ToolError(
            "予測デプロイメントが設定されていません。"
            "FORECAST_DEPLOYMENT_ID 環境変数を設定してください。"
        )

    if not scoring_dataset_id:
        raise ToolError(
            "スコアリングデータセットが設定されていません。"
            "SCORING_DATASET_ID 環境変数を設定してください。"
        )

    if not target_month or not target_month.strip():
        raise ToolError("予測対象月 (target_month) を指定してください。例: 2026-04")

    logger.info(
        f"売上予測を実行: target_month={target_month}, store_type={store_type}, "
        f"deployment={forecast_deployment_id}"
    )

    try:
        deployment = dr.Deployment.get(forecast_deployment_id)

        # スコアリングデータセットを使用して予測を実行
        job = deployment.predict_with_dataset(
            dataset_id=scoring_dataset_id,
            max_wait=600,
        )

        # 予測結果を取得
        predictions = job if isinstance(job, dict) else {"message": "予測が完了しました"}

        result = {
            "target_month": target_month,
            "store_type": store_type,
            "deployment_id": forecast_deployment_id,
            "predictions": predictions,
            "note": "DataRobot時系列モデルによる予測結果です。",
        }

        # 業態でフィルタリング（全体以外の場合）
        if store_type != "全体":
            result["filter_applied"] = f"業態: {store_type}"

        return ToolResult(structured_content=result)

    except Exception as e:
        logger.error(f"売上予測の実行に失敗しました: {e}")
        raise ToolError(f"売上予測の実行に失敗しました: {str(e)}")
