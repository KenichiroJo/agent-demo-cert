"""
小売売上予測の誤差分析モジュール
ERCOTリファレンス: forecast-agent-main/backend/ercot/analysis.py

AsyncOpenAI SDK → DataRobot LLM Gateway (OpenAI互換) を使用
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml  # type: ignore
from openai import AsyncOpenAI

from app.retail._vdb_search import search_vdb
from app.retail.runtime_params import get_runtime_param


def _llm_base_url(endpoint: str) -> str:
    """DataRobot エンドポイントから LLM Gateway URL を構築"""
    base = endpoint.rstrip("/")
    if base.endswith("/api/v2"):
        base = base[: -len("/api/v2")]
    return f"{base}/api/v2/genai/llmgw"


# カタログから取得したモデルをキャッシュ
_cached_model: str | None = None


async def _get_available_model(endpoint: str, token: str) -> str:
    """LLM Gateway カタログから利用可能なモデルを自動検出"""
    global _cached_model
    if _cached_model:
        return _cached_model

    # 環境変数で明示指定されている場合はそれを使う
    env_model = os.getenv("LLM_DEFAULT_MODEL")
    if env_model:
        _cached_model = env_model
        return env_model

    # カタログ API を呼んで利用可能モデルを取得
    base = endpoint.rstrip("/")
    catalog_url = f"{base}/genai/llmgw/catalog/"
    headers = {"Authorization": f"Bearer {token}"}

    # 優先順位: コスト効率・日本語対応・速度のバランス
    # NOTE: azure/gpt-4o-mini は2026年にリタイア済み
    preferred = [
        "azure/gpt-4o",
        "azure/gpt-4o-2024-11-20",
        "azure/gpt-5-mini",
        "azure/gpt-5-nano",
        "azure/gpt-5",
        "anthropic/claude-sonnet-4-20250514",
        "anthropic/claude-3-haiku",
        "bedrock/anthropic.claude-sonnet-4",
        "bedrock/anthropic.claude-3-5-haiku",
    ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(catalog_url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])

        available = [
            m["model"] for m in data
            if m.get("status") == "active"
        ]
        print(f"[LLM Gateway] カタログ: {len(available)} モデル利用可能")
        print(f"[LLM Gateway] 例: {available[:10]}")

        # 優先リストから最初にマッチするものを選択
        for pref in preferred:
            for avail in available:
                if pref in avail:
                    _cached_model = avail
                    print(f"[LLM Gateway] 選択モデル: {_cached_model}")
                    return _cached_model

        # 優先リストにマッチしない場合は最初の利用可能モデル
        if available:
            _cached_model = available[0]
            print(f"[LLM Gateway] フォールバックモデル: {_cached_model}")
            return _cached_model

    except Exception as e:
        print(f"[LLM Gateway] カタログ取得エラー: {e}")

    # 最終フォールバック
    fallback = "azure/gpt-4o"
    print(f"[LLM Gateway] 最終フォールバック: {fallback}")
    return fallback


_AGENTS_YAML_CACHE: dict[str, Any] | None = None


def _load_agents_yaml() -> dict[str, Any]:
    global _AGENTS_YAML_CACHE
    if _AGENTS_YAML_CACHE is not None:
        return _AGENTS_YAML_CACHE
    path = Path(__file__).parent / "agents.yaml"
    _AGENTS_YAML_CACHE = yaml.safe_load(path.read_text()) or {}
    return _AGENTS_YAML_CACHE


def _build_base_context(
    *, data_point: dict[str, Any], error_context: dict[str, Any]
) -> str:
    """データポイントと誤差コンテキストから分析用テキストを構築"""

    def fmt(value: Any, default: str = "0", f: str = ".2f") -> str:
        try:
            return format(float(value), f) if value is not None else default
        except Exception:
            return default

    return f"""
予測誤差データ:
業態: {data_point.get("store_type")}
対象月: {data_point.get("year_month")}
実績売上: {fmt(data_point.get("sales_billion_yen"))}億円
予測売上: {fmt(data_point.get("predicted_sales"))}億円
予測誤差: {fmt(data_point.get("forecast_error"), f="+.3f")}億円 ({fmt(data_point.get("pct_error"), f="+.1f")}%)

誤差コンテキスト:
業態RMSE: {fmt(error_context.get("store_type_rmse"))}億円
業態MAE: {fmt(error_context.get("store_type_mae"))}億円
業態内パーセンタイル: 上位{fmt(error_context.get("overall_percentile"), f=".0f")}%
Zスコア: {fmt(error_context.get("z_score"))}
同月RMSE: {fmt(error_context.get("month_rmse", "N/A"))}億円
同季節RMSE: {fmt(error_context.get("season_rmse", "N/A"))}億円
""".strip()


def _build_time_series_context(surrounding_data: str) -> str:
    """周辺時系列データのコンテキストを構築"""
    return f"""
同業態の売上推移 (直近データ):
{surrounding_data}
""".strip()


async def analyze_retail_forecast_error(
    *,
    data_point: dict[str, Any],
    error_context: dict[str, Any],
    surrounding_data: str,
    datarobot_token: str | None = None,
) -> dict[str, Any]:
    """
    小売売上予測の誤差を LLM で分析する

    ERCOTリファレンスの analyze_forecast_error() と同等のパターン:
    1. agents.yaml からロール・ゴール・バックストーリーを読み込み
    2. データコンテキストを構築
    3. AsyncOpenAI SDK で LLM Gateway を呼び出し
    4. 構造化された分析結果を返す
    """
    endpoint = get_runtime_param("DATAROBOT_ENDPOINT")
    api_key = datarobot_token or get_runtime_param("DATAROBOT_API_TOKEN")

    store_type = str(data_point.get("store_type", "不明"))
    date_str = str(data_point.get("year_month", ""))
    error_val = data_point.get("forecast_error", 0)

    # agents.yaml からエージェント設定を読み込み
    agents_cfg = _load_agents_yaml()
    agent_cfg = (agents_cfg.get("agents") or {}).get("retail_analyst") or {}
    task_cfg = (agents_cfg.get("tasks") or {}).get("error_analysis") or {}

    # タスク記述テンプレートの展開
    task_description_tpl = str(task_cfg.get("description") or "")
    task_description = task_description_tpl.format(
        store_type=store_type,
        date=date_str,
        error=f"{float(error_val or 0):.3f}",
    )

    # VDB検索: 業態と時期に関連する外部レポートを取得
    vdb_id = get_runtime_param("VDB_DEPLOYMENT_ID")
    vdb_section = ""
    if vdb_id:
        try:
            vdb_query = f"{store_type} {date_str[:7] if len(date_str) > 7 else date_str} 売上 市場動向"
            vdb_docs = await search_vdb(vdb_query, vdb_id, max_results=2)
            if vdb_docs:
                print(f"[VDB] Error analysis: query='{vdb_query}', results={len(vdb_docs)} docs")
                vdb_section = "\n\n参考: 外部レポート（経産省EC市場調査等）:\n" + "\n---\n".join(vdb_docs)
            else:
                print(f"[VDB] Error analysis: query='{vdb_query}', results=0 docs")
        except Exception as e:
            print(f"[VDB] Error analysis error: {e}")

    # ユーザープロンプト構築
    user_prompt = "\n\n".join(
        [
            task_description.strip(),
            _build_base_context(data_point=data_point, error_context=error_context),
            _build_time_series_context(surrounding_data),
            vdb_section,
            "",
            "重要: 以下の構成で回答してください：",
            "1. **誤差の概要** (1-2文): 何がどのくらい外れたか",
            "2. **根本原因分析** (3-5項目): 各要因を具体的な数値とともに説明。外部レポートがある場合は引用してください",
            "3. **時系列パターン分析**: 売上推移データから読み取れるトレンドや異常",
            "4. **改善提案** (2-3項目): 予測精度向上のための具体的アクション",
        ]
    )

    # AsyncOpenAI SDK で LLM Gateway 呼び出し (ERCOT と同じパターン)
    client = AsyncOpenAI(
        api_key=api_key or "dummy-key",
        base_url=_llm_base_url(endpoint),
        timeout=90.0,
    )
    model = await _get_available_model(endpoint, api_key)
    max_tokens = int(os.getenv("RETAIL_ANALYSIS_MAX_TOKENS") or "2000")

    print(f"[LLM Gateway] model={model}, base_url={_llm_base_url(endpoint)}")

    summary_text = ""
    llm_error_detail = ""
    try:
        print(f"[LLM Gateway] Sending request... endpoint={endpoint}, api_key={'SET' if api_key else 'EMPTY'}")
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"役割: {agent_cfg.get('role', '小売・EC業界 売上予測アナリスト')}\n"
                        f"目標: {agent_cfg.get('goal', '')}\n\n"
                        f"バックストーリー:\n{agent_cfg.get('backstory', '')}\n\n"
                        "タスクの指示と出力フォーマットに正確に従ってください。"
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        summary_text = completion.choices[0].message.content or ""
        print(f"[LLM Gateway] Response: {len(summary_text)} chars")
    except Exception as e:
        llm_error_detail = f"{type(e).__name__}: {e}"
        print(f"[LLM Gateway] Error: {llm_error_detail}")
        import traceback
        traceback.print_exc()

    # フォールバック: LLM が空を返した場合 → エラー詳細を表示
    if not summary_text:
        error_info = llm_error_detail or "空レスポンス"
        summary_text = (
            f"## 誤差の概要\n\n"
            f"**{store_type}** の {date_str} における予測誤差は "
            f"**{abs(float(error_val or 0)):.3f}億円** でした。\n\n"
            f"## ⚠️ LLM Gateway エラー\n\n"
            f"```\n"
            f"URL: {_llm_base_url(endpoint)}/chat/completions\n"
            f"Model: {model}\n"
            f"Error: {error_info}\n"
            f"DATAROBOT_ENDPOINT: {endpoint}\n"
            f"DATAROBOT_API_TOKEN: {'設定済み' if api_key else '未設定'}\n"
            f"```\n\n"
            f"## 統計コンテキスト\n\n"
            f"- 業態 RMSE: {error_context.get('store_type_rmse', 'N/A')}億円\n"
            f"- 業態 MAE: {error_context.get('store_type_mae', 'N/A')}億円\n"
            f"- パーセンタイル: 上位 {error_context.get('overall_percentile', 'N/A')}%\n"
        )

    # 信頼度スコア: 誤差の大きさに反比例
    pct_error = abs(float(data_point.get("pct_error", 0) or 0))
    confidence = max(0.3, min(0.95, 1.0 - pct_error / 50))

    return {
        "analysis": {
            "summary": summary_text,
        },
        "hypothesis": summary_text,
        "confidence_score": confidence,
        "supporting_evidence": [],
        "recommendations": [],
    }
