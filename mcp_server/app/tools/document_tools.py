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


@dr_mcp_tool(tags={"rag", "documents", "ec_market", "retail"})
async def search_ec_market_documents(
    query: Annotated[
        str,
        "検索クエリ（EC市場動向、消費者トレンド、小売業界に関する質問）",
    ],
) -> ToolResult:
    """EC市場調査レポートや消費者動向資料をベクターDB検索します。

    経済産業省「電子商取引に関する市場調査」や総務省「家計調査」等の
    公開文献から、クエリに関連する情報を検索して返します。
    市場トレンド、EC化率、消費者動向等の質問に活用してください。
    """
    config = get_user_config()
    vdb_deployment_id = config.vdb_deployment_id

    if not vdb_deployment_id:
        raise ToolError(
            "ベクターDBデプロイメントが設定されていません。"
            "VDB_DEPLOYMENT_ID 環境変数を設定してください。"
        )

    if not query or not query.strip():
        raise ToolError("検索クエリを指定してください。")

    logger.info(
        f"文書検索を実行: query='{query}', deployment={vdb_deployment_id}"
    )

    try:
        deployment = dr.Deployment.get(vdb_deployment_id)

        # VDBデプロイメントに対して検索クエリを送信
        import pandas as pd

        input_df = pd.DataFrame({"promptText": [query]})
        predictions = deployment.predict(input_df)

        # 検索結果を構造化して返却
        result = {
            "query": query,
            "deployment_id": vdb_deployment_id,
            "results": predictions.to_dict(orient="records")
            if hasattr(predictions, "to_dict")
            else str(predictions),
            "source": "経済産業省 EC市場調査 / 総務省 家計調査",
            "note": "ベクターDB検索による関連文書の抽出結果です。引用元を明記して回答してください。",
        }

        return ToolResult(structured_content=result)

    except Exception as e:
        logger.error(f"文書検索の実行に失敗しました: {e}")
        raise ToolError(f"文書検索の実行に失敗しました: {str(e)}")
