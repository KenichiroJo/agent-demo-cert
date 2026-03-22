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
# ------------------------------------------------------------------------------
"""
Prompt management module for the retail/EC demand forecasting agent.
Supports fetching versioned prompts from DataRobot Prompt Template API
with fallback to a default prompt.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.config import Config

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """\
あなたは小売・EC売上予測アシスタントです。
経済産業省「商業動態統計」をベースとした業態別（百貨店、スーパー、コンビニ、ドラッグストア、EC）の\
月次販売額データと、EC市場調査レポート等の公開文献を活用して、ユーザーの質問に正確に回答してください。

## 利用可能なツールと使い分け

1. **データクエリツール（DARIA）**: 過去の売上データに関する質問に使用
   - 例: 「2024年のコンビニ売上合計は？」「百貨店の売上推移を教えて」
   - データセットのスキーマ情報も確認できます

2. **売上予測ツール**: 将来の売上予測に関する質問に使用
   - 例: 「来月のスーパー売上を予測して」「2026年4月のEC売上は？」
   - DataRobotの時系列予測モデルを使用した統計的予測を返します

3. **文書検索ツール（RAG）**: EC市場トレンドやレポートに関する質問に使用
   - 例: 「EC市場の成長率は？」「消費者動向の最新トレンドは？」
   - 経済産業省のEC市場調査レポート等から関連情報を検索します

## 回答のガイドライン

- データに基づいた正確な回答を心がけ、具体的な数値を含めてください
- 予測値と実績値を明確に区別してください
- 文書検索結果を使用する場合は、引用元を明記してください
- 複数のツールを組み合わせて包括的な分析を提供してください
- 日本語で丁寧に回答してください
"""


def fetch_rendered_prompt(config: "Config") -> str:
    """Fetch a rendered prompt from DataRobot Prompt Template API.

    If prompt_template_id is configured, attempts to fetch and render
    the prompt template from DataRobot. Falls back to DEFAULT_PROMPT
    on any error or if prompt_template_id is not set.

    Args:
        config: Agent configuration containing prompt_template_id and
                other variables for template rendering.

    Returns:
        The rendered prompt string.
    """
    if not config.prompt_template_id:
        logger.info(
            "PROMPT_TEMPLATE_ID が未設定のため、デフォルトプロンプトを使用します。"
        )
        return DEFAULT_PROMPT

    try:
        import datarobot as dr

        logger.info(
            f"DataRobot Prompt Template を取得中: {config.prompt_template_id}"
        )

        # Fetch the prompt template from DataRobot
        prompt_template = dr.models.genai.prompt_template.PromptTemplate.get(
            config.prompt_template_id
        )

        # Get the latest version
        versions = prompt_template.versions
        if not versions:
            logger.warning(
                "Prompt Template にバージョンが存在しません。デフォルトプロンプトを使用します。"
            )
            return DEFAULT_PROMPT

        target_version = versions[0]  # Latest version

        # Render with variables
        render_variables = {
            "company_name": config.company_name or "小売EC売上予測デモ",
        }

        # Add optional variables if available
        if config.forecast_deployment_id:
            render_variables["forecast_deployment_id"] = config.forecast_deployment_id
        if config.scoring_dataset_id:
            render_variables["scoring_dataset_id"] = config.scoring_dataset_id

        rendered = target_version.render(variables=render_variables)
        logger.info("Prompt Template のレンダリングが完了しました。")
        return rendered

    except ImportError:
        logger.warning(
            "datarobot パッケージが利用できません。デフォルトプロンプトを使用します。"
        )
        return DEFAULT_PROMPT
    except Exception as e:
        logger.warning(
            f"Prompt Template の取得に失敗しました: {e}。デフォルトプロンプトを使用します。"
        )
        return DEFAULT_PROMPT
