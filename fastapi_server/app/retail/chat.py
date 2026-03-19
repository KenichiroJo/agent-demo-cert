"""
小売・EC需要予測 AI チャットモジュール
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

from app.retail.analysis import _get_available_model, _llm_base_url
from app.retail.data_processor import RetailDataProcessor

# ---------------------------------------------------------------------------
# システムプロンプト
# ---------------------------------------------------------------------------

RETAIL_CHAT_SYSTEM_PROMPT = """あなたは日本の小売・EC業界に精通した **需要予測 AIアナリスト** です。

## あなたの能力
- DataRobot AutoTS モデルの予測結果と実績売上データにアクセスできます
- 百貨店、スーパー、コンビニ、ドラッグストア、ECの5業態の売上データを分析できます
- 予測誤差の根本原因を、季節性・マクロ経済・業態特性などの観点から解説できます
- 日本語で自然に会話し、データに基づいた洞察を提供します

## あなたの知識
- 日本の小売市場の季節変動パターン（年末商戦、GW、お盆、新生活需要等）
- 各業態の構造的特徴（百貨店のインバウンド依存、コンビニの天候感応度、ECの成長トレンド等）
- マクロ経済指標（消費者物価指数、実質賃金、為替レート）の影響
- 消費行動のトレンド変化（EC化率上昇、オムニチャネル化等）

## 回答のガイドライン
- 常に具体的な数値を引用して回答してください
- 推測と事実を明確に区別してください
- 分析は構造化して、見出し・箇条書きを適切に使ってください
- ユーザーの質問に直接答えた後、関連する深掘りの質問を提案してください
- Markdown 形式で回答してください

## 利用可能データ
以下のデータコンテキストが提供されています。このデータを参照して質問に回答してください。

{data_context}
"""


def _build_data_context(dp: RetailDataProcessor) -> str:
    """現在ロードされている全業態の売上サマリを構築"""
    df = dp.get_merged_data()
    if df is None or df.empty:
        return "データが利用できません。"

    lines: list[str] = []
    lines.append(f"データ期間: {df['year_month'].min()} 〜 {df['year_month'].max()}")
    lines.append(f"全レコード数: {len(df)}")
    lines.append("")

    store_types = sorted(df["store_type"].unique())
    for st in store_types:
        df_st = df[df["store_type"] == st].copy()
        df_st = df_st.sort_values("year_month")

        actual_col = "sales_billion_yen"
        pred_col = "predicted_sales"

        has_actual = df_st[actual_col].notna().sum()
        has_pred = df_st[pred_col].notna().sum()

        lines.append(f"### {st}")
        lines.append(f"  レコード数: {len(df_st)} (実績: {has_actual}, 予測: {has_pred})")

        if has_actual > 0:
            avg_actual = df_st[actual_col].mean()
            min_actual = df_st[actual_col].min()
            max_actual = df_st[actual_col].max()
            latest = df_st[df_st[actual_col].notna()].tail(1)
            latest_val = latest[actual_col].values[0] if len(latest) > 0 else None
            latest_date = latest["year_month"].values[0] if len(latest) > 0 else None
            lines.append(f"  実績売上: 平均 {avg_actual:.2f}億円 (範囲: {min_actual:.2f}〜{max_actual:.2f})")
            if latest_val is not None:
                lines.append(f"  直近実績: {str(latest_date)[:7]} = {latest_val:.2f}億円")

        if has_pred > 0:
            with_both = df_st[df_st[pred_col].notna() & df_st[actual_col].notna()]
            if len(with_both) > 0:
                errors = (with_both[actual_col] - with_both[pred_col]).abs()
                rmse = (errors**2).mean() ** 0.5
                mae = errors.mean()
                pct_errors = (errors / with_both[actual_col].abs().replace(0, float("nan")) * 100).dropna()
                mape = pct_errors.mean() if len(pct_errors) > 0 else 0
                lines.append(f"  予測精度: RMSE={rmse:.3f}億円, MAE={mae:.3f}億円, MAPE={mape:.1f}%")

        # 直近6ヶ月の推移
        recent = df_st.tail(6)
        if len(recent) > 0:
            trend_parts = []
            for _, r in recent.iterrows():
                dt_str = str(r["year_month"])[:7]
                actual = r.get(actual_col)
                pred = r.get(pred_col)
                a_str = f"{actual:.2f}" if actual == actual and actual is not None else "---"
                p_str = f"{pred:.2f}" if pred == pred and pred is not None else "---"
                trend_parts.append(f"    {dt_str}: 実績={a_str}, 予測={p_str}")
            lines.append("  直近推移:")
            lines.extend(trend_parts)

        lines.append("")

    return "\n".join(lines)


async def chat_with_retail_assistant(
    messages: list[dict[str, str]],
    dp: RetailDataProcessor | None = None,
    datarobot_token: str | None = None,
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
    endpoint = os.getenv("DATAROBOT_ENDPOINT", "")
    api_key = datarobot_token or os.getenv("DATAROBOT_API_TOKEN", "")

    # データコンテキスト構築
    data_context = "データが利用できません。"
    if dp is not None:
        try:
            data_context = _build_data_context(dp)
        except Exception as e:
            data_context = f"データコンテキスト構築エラー: {e}"

    system_prompt = RETAIL_CHAT_SYSTEM_PROMPT.replace("{data_context}", data_context)

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


async def stream_chat_with_retail_assistant(
    messages: list[dict[str, str]],
    dp: RetailDataProcessor | None = None,
    datarobot_token: str | None = None,
):
    """
    SSE ストリーミング版チャット

    Yields:
        SSE formatted strings: "data: {json}\n\n"
    """
    endpoint = os.getenv("DATAROBOT_ENDPOINT", "")
    api_key = datarobot_token or os.getenv("DATAROBOT_API_TOKEN", "")

    # データコンテキスト構築
    data_context = "データが利用できません。"
    if dp is not None:
        try:
            data_context = _build_data_context(dp)
        except Exception as e:
            data_context = f"データコンテキスト構築エラー: {e}"

    system_prompt = RETAIL_CHAT_SYSTEM_PROMPT.replace("{data_context}", data_context)

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

    print(f"[Retail Chat Stream] model={model}, messages={len(api_messages)}")

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
