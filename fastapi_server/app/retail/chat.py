"""
小売・EC売上予測 AI チャットモジュール
LLM Gateway を使って対話形式で売上データを分析する

- チャット履歴を保持してマルチターン会話を実現
- 売上データコンテキストを自動で LLM に提供
- SSE ストリーミングでリアルタイムに応答を返す
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import AsyncOpenAI

from app.retail._vdb_search import search_vdb
from app.retail.analysis import _get_available_model, _llm_base_url
from app.retail.data_processor import RetailDataProcessor
from app.retail.runtime_params import get_runtime_param

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

RETAIL_CHAT_SYSTEM_PROMPT = """あなたは日本の小売・EC業界に精通した **売上予測 AIアナリスト** です。

## あなたの能力
- DataRobot AutoTS モデルの予測結果と実績売上データにアクセスできます
- EC1、EC2、EC3、EC4、EC5の5業態の売上データを分析できます
- 予測誤差の根本原因を、季節性・マクロ経済・業態特性などの観点から解説できます
- 日本語で自然に会話し、データに基づいた洞察を提供します

## あなたの知識
- 日本の小売市場の季節変動パターン（年末商戦、GW、お盆、新生活需要等）
- 各業態の構造的特徴と季節変動パターン
- マクロ経済指標（消費者物価指数、実質賃金、為替レート）の影響
- 消費行動のトレンド変化（EC化率上昇、オムニチャネル化等）

## 回答のガイドライン
- 常に具体的な数値を引用して回答してください
- 推測と事実を明確に区別してください
- 分析は構造化して、見出し・箇条書きを適切に使ってください
- **データを参照する際は、必ず Markdown テーブル（表）を使ってください**
- ユーザーの質問に直接答えた後、関連する深掘りの質問を提案してください
- Markdown 形式で回答してください

## 利用可能データ
以下のデータコンテキストが提供されています。このデータを参照して質問に回答してください。

{data_context}

## 外部レポートデータ（経産省EC市場調査等）
以下はVectorDatabaseから取得した関連ドキュメントです。分析の裏付けとして活用してください。
出典情報がある場合は必ず引用してください。

{vdb_context}
"""


def _build_data_context(dp: RetailDataProcessor, store_type: str | None = None) -> str:
    """
    売上データコンテキストを構築

    store_type 指定時: その業態の全月データをMarkdown表形式 + 他業態は1行サマリ
    store_type 未指定時: 全業態サマリ
    """
    df = dp.get_merged_data()
    if df is None or df.empty:
        return "データが利用できません。"

    actual_col = "sales_billion_yen"
    pred_col = "predicted_sales"

    lines: list[str] = []
    lines.append(f"データ期間: {df['year_month'].min()} 〜 {df['year_month'].max()}")
    lines.append(f"全レコード数: {len(df)}")

    if store_type:
        lines.append(f"\n**ユーザーは「{store_type}」について分析中です。**\n")

    all_store_types = sorted(df["store_type"].unique())

    for st in all_store_types:
        df_st = df[df["store_type"] == st].copy()
        df_st = df_st.sort_values("year_month")

        has_actual = df_st[actual_col].notna().sum()
        has_pred = df_st[pred_col].notna().sum()

        is_focus = (store_type is None) or (st == store_type)

        if not is_focus:
            # 非対象業態は1行サマリのみ
            avg = df_st[actual_col].mean() if has_actual > 0 else 0
            lines.append(f"- {st}: 平均売上 {avg:.2f}億円 ({len(df_st)}件)")
            continue

        # 対象業態の詳細
        lines.append(f"\n### {st}")
        lines.append(f"レコード数: {len(df_st)} (実績: {has_actual}, 予測: {has_pred})")

        if has_actual > 0:
            avg_actual = df_st[actual_col].mean()
            min_actual = df_st[actual_col].min()
            max_actual = df_st[actual_col].max()
            lines.append(f"実績売上: 平均 {avg_actual:.2f}億円 (範囲: {min_actual:.2f}〜{max_actual:.2f})")

        if has_pred > 0:
            with_both = df_st[df_st[pred_col].notna() & df_st[actual_col].notna()]
            if len(with_both) > 0:
                errors = (with_both[actual_col] - with_both[pred_col]).abs()
                rmse = (errors**2).mean() ** 0.5
                mae = errors.mean()
                pct_errors = (errors / with_both[actual_col].abs().replace(0, float("nan")) * 100).dropna()
                mape = pct_errors.mean() if len(pct_errors) > 0 else 0
                lines.append(f"予測精度: RMSE={rmse:.3f}億円, MAE={mae:.3f}億円, MAPE={mape:.1f}%")

        # 全月データをMarkdown表形式で出力
        data_rows = []
        for _, r in df_st.iterrows():
            dt_str = str(r["year_month"])[:7]
            actual = r.get(actual_col)
            pred = r.get(pred_col)
            err = r.get("forecast_error")
            pct = r.get("pct_error")
            a_str = f"{actual:.2f}" if actual == actual and actual is not None else ""
            p_str = f"{pred:.2f}" if pred == pred and pred is not None else ""
            e_str = f"{err:+.3f}" if err == err and err is not None else ""
            pct_str = f"{pct:+.1f}%" if pct == pct and pct is not None else ""
            data_rows.append(f"| {dt_str} | {a_str} | {p_str} | {e_str} | {pct_str} |")

        if data_rows:
            lines.append("\n全月データ:")
            lines.append("| 年月 | 実績(億円) | 予測(億円) | 誤差(億円) | 誤差率 |")
            lines.append("|------|-----------|-----------|-----------|--------|")
            lines.extend(data_rows)

        lines.append("")

    return "\n".join(lines)


async def chat_with_retail_assistant(
    messages: list[dict[str, str]],
    dp: RetailDataProcessor | None = None,
    datarobot_token: str | None = None,
    store_type: str | None = None,
) -> str:
    """
    マルチターン対話で小売データを分析する

    Args:
        messages: チャット履歴 [{"role": "user"|"assistant", "content": "..."}]
        dp: データプロセッサ（売上データコンテキスト用）
        datarobot_token: DataRobot API トークン

    Returns:
        LLM のレスポンステキスト
    """
    endpoint = get_runtime_param("DATAROBOT_ENDPOINT")
    api_key = datarobot_token or get_runtime_param("DATAROBOT_API_TOKEN")

    # データコンテキスト構築
    data_context = "データが利用できません。"
    if dp is not None:
        try:
            data_context = _build_data_context(dp, store_type=store_type)
        except Exception as e:
            data_context = f"データコンテキスト構築エラー: {e}"

    # VDB検索
    last_user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    vdb_context = await _fetch_vdb_context(last_user_msg)

    system_prompt = (
        RETAIL_CHAT_SYSTEM_PROMPT
        .replace("{data_context}", data_context)
        .replace("{vdb_context}", vdb_context)
    )

    # OpenAI API メッセージ配列を構築
    api_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            api_messages.append({"role": role, "content": content})

    # LLM Gateway 呼び出し
    client = AsyncOpenAI(
        api_key=api_key or "dummy-key",
        base_url=_llm_base_url(endpoint),
        timeout=120.0,
    )
    model = await _get_available_model(endpoint, api_key)
    max_tokens = int(os.getenv("RETAIL_CHAT_MAX_TOKENS", "3000"))

    print(f"[Retail Chat] model={model}, messages={len(api_messages)}, data_context_len={len(data_context)}")

    completion = await client.chat.completions.create(
        model=model,
        messages=api_messages,  # type: ignore
        max_tokens=max_tokens,
        temperature=0.7,
    )

    response_text = completion.choices[0].message.content or ""
    print(f"[Retail Chat] Response: {len(response_text)} chars")
    return response_text


async def _fetch_vdb_context(query: str) -> str:
    """ユーザーの質問でVDB検索し、関連ドキュメントコンテキストを返す"""
    vdb_id = get_runtime_param("VDB_DEPLOYMENT_ID")
    if not vdb_id or not query:
        return "外部レポートはありません。"

    try:
        docs = await search_vdb(query, vdb_id, max_results=3)
        if docs:
            print(f"[VDB] query='{query[:50]}...', results={len(docs)} docs")
            return "\n\n---\n\n".join(docs)
        else:
            print(f"[VDB] query='{query[:50]}...', results=0 docs")
            return "外部レポートはありません。"
    except Exception as e:
        print(f"[VDB] Error: {e}")
        return "外部レポートの取得に失敗しました。"


async def stream_chat_with_retail_assistant(
    messages: list[dict[str, str]],
    dp: RetailDataProcessor | None = None,
    datarobot_token: str | None = None,
    store_type: str | None = None,
):
    """
    SSE ストリーミング版チャット

    Yields:
        SSE formatted strings: "data: {json}\n\n"
    """
    endpoint = get_runtime_param("DATAROBOT_ENDPOINT")
    api_key = datarobot_token or get_runtime_param("DATAROBOT_API_TOKEN")

    # データコンテキスト構築
    data_context = "データが利用できません。"
    if dp is not None:
        try:
            data_context = _build_data_context(dp, store_type=store_type)
        except Exception as e:
            data_context = f"データコンテキスト構築エラー: {e}"

    # VDB検索: ユーザーの最新メッセージで外部レポートを取得
    last_user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    vdb_context = await _fetch_vdb_context(last_user_msg)

    system_prompt = (
        RETAIL_CHAT_SYSTEM_PROMPT
        .replace("{data_context}", data_context)
        .replace("{vdb_context}", vdb_context)
    )

    api_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            api_messages.append({"role": role, "content": content})

    client = AsyncOpenAI(
        api_key=api_key or "dummy-key",
        base_url=_llm_base_url(endpoint),
        timeout=120.0,
    )
    model = await _get_available_model(endpoint, api_key)
    max_tokens = int(os.getenv("RETAIL_CHAT_MAX_TOKENS", "3000"))

    print(f"[Retail Chat Stream] model={model}, messages={len(api_messages)}, store_type={store_type}, vdb={'有' if vdb_context != '外部レポートはありません。' else '無'}")

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=api_messages,  # type: ignore
            max_tokens=max_tokens,
            temperature=0.7,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield f"data: {json.dumps({'type': 'delta', 'content': delta.content}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"[Retail Chat Stream] Error: {error_msg}")
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
