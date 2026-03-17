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

from datarobot_genai.drmcp import dr_mcp_tool
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger(__name__)


@dr_mcp_tool(tags={"data", "schema", "retail"})
async def get_retail_data_schema() -> ToolResult:
    """小売・EC売上データセットのスキーマ情報を返します。
    DARIAツールでデータクエリを行う前に、データ構造を確認するために使用してください。
    """
    schema_info = {
        "dataset_name": "小売・EC売上時系列データ",
        "description": "経済産業省「商業動態統計」をベースにした小売業態別月次販売額データ",
        "period": "2015年1月〜2025年12月（132ヶ月）",
        "total_rows": 660,
        "series_id": "store_type",
        "store_types": ["百貨店", "スーパー", "コンビニ", "ドラッグストア", "EC"],
        "columns": {
            "year_month": {
                "type": "date",
                "format": "YYYY-MM-01",
                "description": "年月（日付カラム）",
            },
            "store_type": {
                "type": "string",
                "description": "業態（シリーズID）",
            },
            "sales_billion_yen": {
                "type": "float",
                "description": "月次販売額（十億円）- ターゲット変数",
            },
            "month": {
                "type": "int",
                "description": "月（1-12、季節性キャプチャ用）",
            },
            "is_bonus_month": {
                "type": "bool",
                "description": "ボーナス月フラグ（6月・12月=True）",
            },
            "is_golden_week": {
                "type": "bool",
                "description": "ゴールデンウィーク月フラグ（5月=True）",
            },
            "is_year_end": {
                "type": "bool",
                "description": "年末商戦月フラグ（11月・12月=True）",
            },
            "consumer_confidence_index": {
                "type": "float",
                "description": "消費者態度指数（内閣府公開データ準拠）",
            },
            "cpi": {
                "type": "float",
                "description": "消費者物価指数（総務省公開データ準拠）",
            },
            "avg_temperature": {
                "type": "float",
                "description": "月平均気温・東京（気象庁データ準拠）",
            },
            "unemployment_rate": {
                "type": "float",
                "description": "完全失業率（総務省公開データ準拠）",
            },
            "num_holidays": {
                "type": "int",
                "description": "月内祝日数",
            },
        },
    }

    logger.info("Retail data schema requested")
    return ToolResult(structured_content=schema_info)
