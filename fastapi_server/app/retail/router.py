"""
小売需要予測ダッシュボード API ルーター
リファレンス: forecast-agent-main/backend/routers/ercot_api.py
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import date, datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.retail.data_processor import RetailDataProcessor
from app.retail.error_analyzer import RetailErrorAnalyzer
from app.retail.utils import clean_nan_values

retail_router = APIRouter()

data_processor: Optional[RetailDataProcessor] = None
error_analyzer: Optional[RetailErrorAnalyzer] = None
_init_error: Optional[str] = None


def _ensure_initialized() -> None:
    global data_processor, error_analyzer, _init_error
    if data_processor and error_analyzer:
        return
    try:
        data_processor = RetailDataProcessor()
        error_analyzer = RetailErrorAnalyzer()
        _init_error = None
    except Exception as e:
        data_processor = None
        error_analyzer = None
        _init_error = str(e)
        raise


def _dp() -> RetailDataProcessor:
    _ensure_initialized()
    assert data_processor is not None
    return data_processor


def _ea() -> RetailErrorAnalyzer:
    _ensure_initialized()
    assert error_analyzer is not None
    return error_analyzer


class ErrorAnalysisRequest(BaseModel):
    store_type: str
    date: str


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@retail_router.get("/store-types")
async def get_store_types():
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    return {"status": "success", "store_types": _dp().get_store_types()}


@retail_router.get("/status")
async def get_status():
    status: Dict[str, Any] = {"initialized": False, "init_error": _init_error}
    try:
        _ensure_initialized()
        status["initialized"] = True
        dp = _dp()
        status["data_source"] = dp.data_source
        status["record_count"] = len(dp.merged_data) if dp.merged_data is not None else 0
    except Exception:
        pass
    return status


@retail_router.get("/date-range")
async def get_date_range():
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    dr = _dp().get_date_range()
    return {"status": "success", "start_date": dr["start"], "end_date": dr["end"]}


@retail_router.get("/forecast-data")
async def get_forecast_data(
    store_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: Optional[int] = 1000,
):
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    data = _dp().get_forecast_data(store_type=store_type, start_date=start_date, end_date=end_date, limit=limit)
    return clean_nan_values({"status": "success", "count": len(data), "data": data})


@retail_router.get("/error-metrics")
async def get_error_metrics(store_type: Optional[str] = None):
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    metrics = _ea().calculate_metrics(_dp().get_merged_data(), store_type=store_type)
    return clean_nan_values({"status": "success", "metrics": metrics})


@retail_router.get("/outliers")
async def get_outliers(store_type: Optional[str] = None, threshold: float = 2.0, limit: int = 100):
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    outliers = _ea().detect_outliers(_dp().get_merged_data(), store_type=store_type, threshold=threshold, limit=limit)
    return clean_nan_values({"status": "success", "threshold": threshold, "count": len(outliers), "outliers": outliers})


def _build_surrounding_context(dp: RetailDataProcessor, store_type: str, target_date: datetime) -> str:
    """対象ポイントの前後6ヶ月のデータを整形して返す"""
    import pandas as pd

    df = dp.get_merged_data()
    df_st = df[(df["store_type"] == store_type) & (df["predicted_sales"].notna())].copy()
    df_st = df_st.sort_values("year_month")

    rows = []
    for _, r in df_st.iterrows():
        dt = r["year_month"]
        if hasattr(dt, "strftime"):
            dt_str = dt.strftime("%Y-%m")
        else:
            dt_str = str(dt)[:7]
        actual = r.get("sales_billion_yen")
        pred = r.get("predicted_sales")
        err = r.get("forecast_error")
        pct = r.get("pct_error")
        rows.append(
            f"  {dt_str}: 実績={actual:.2f}億円, 予測={pred:.2f}億円, "
            f"誤差={err:+.2f}億円 ({pct:+.1f}%)"
            if all(v is not None and v == v for v in [actual, pred, err, pct])
            else f"  {dt_str}: データ不完全"
        )

    return "\n".join(rows[-18:])  # 最新18ヶ月まで


async def _call_llm_gateway(prompt: str, system_prompt: str) -> str:
    """DataRobot LLM Gateway を OpenAI 互換エンドポイントで呼び出す"""
    endpoint = os.getenv("DATAROBOT_ENDPOINT", "")
    token = os.getenv("DATAROBOT_API_TOKEN", "")

    if not endpoint or not token:
        return "(LLM Gateway 未設定: DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN が必要です)"

    # LLM Gateway chat/completions URL
    base = endpoint.rstrip("/")
    url = f"{base}/genai/llmgw/chat/completions"

    model = os.getenv("LLM_DEFAULT_MODEL", "azure/gpt-4.1-mini-2025-04-14")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 2000,
    }

    print(f"[LLM Gateway] Calling {url} with model={model}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json()

    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"[LLM Gateway] Response length: {len(content)} chars")
    return content


async def _analyze_error_stream(request: ErrorAnalysisRequest):
    yield _sse("start", {"status": "started", "message": "分析を開始しました"})

    try:
        _ensure_initialized()
    except Exception:
        yield _sse("error", {"error": f"Not initialized: {_init_error}"})
        return

    target_date = datetime.fromisoformat(request.date)
    data_point = _dp().get_specific_forecast(store_type=request.store_type, target_date=target_date)
    if not data_point:
        yield _sse("error", {"error": "指定された予測データポイントが見つかりません"})
        return

    error_context = _ea().get_error_context(data_point, _dp().get_merged_data())
    error_context = clean_nan_values(error_context)

    actual_sales = float(data_point.get("sales_billion_yen", 0) or 0)
    predicted_sales = float(data_point.get("predicted_sales", 0) or 0)
    error_val = float(data_point.get("forecast_error", 0) or 0)
    pct_error = float(data_point.get("pct_error", 0) or 0)

    yield _sse("heartbeat", {"status": "processing", "message": "LLM に分析を依頼中..."})

    # 周辺データ取得
    surrounding = _build_surrounding_context(_dp(), request.store_type, target_date)

    # LLM プロンプト構築
    system_prompt = (
        "あなたは小売業・EC業界の需要予測の専門アナリストです。\n"
        "DataRobot の AutoTS モデルによる売上予測と実績の乖離について、\n"
        "ビジネス的観点から根本原因を分析してください。\n\n"
        "以下のフォーマットで日本語で回答してください：\n"
        "1. **誤差の概要**: 何がどのくらい外れたか（1-2文）\n"
        "2. **考えられる要因**（3つ以上）: 各要因について具体的に説明\n"
        "   - 季節性・イベント要因\n"
        "   - 消費者行動の変化\n"
        "   - 外部経済要因（物価、為替、政策等）\n"
        "   - 業態特有の構造的要因\n"
        "   - モデルの特性（学習データの偏り等）\n"
        "3. **改善提案**: 予測精度を向上させるための具体的アクション\n\n"
        "分析は具体的な数値に基づき、推測と事実を明確に区別してください。"
    )

    user_prompt = (
        f"## 分析対象\n"
        f"- **業態**: {request.store_type}\n"
        f"- **対象月**: {request.date}\n"
        f"- **実績売上**: {actual_sales:.2f} 億円\n"
        f"- **予測売上**: {predicted_sales:.2f} 億円\n"
        f"- **予測誤差**: {error_val:+.2f} 億円 ({pct_error:+.1f}%)\n"
        f"- **誤差方向**: {'過小予測（実績 > 予測）' if error_val > 0 else '過大予測（予測 > 実績）'}\n\n"
        f"## 統計コンテキスト\n"
        f"- 業態 RMSE: {error_context.get('store_type_rmse', 'N/A')}\n"
        f"- 業態 MAE: {error_context.get('store_type_mae', 'N/A')}\n"
        f"- 全体パーセンタイル: 上位 {error_context.get('overall_percentile', 'N/A')}%\n"
        f"- Z スコア: {error_context.get('z_score', 'N/A')}\n\n"
        f"## 同業態の直近売上推移\n{surrounding}\n\n"
        f"上記データに基づき、この予測誤差の根本原因を分析してください。"
    )

    # LLM Gateway 呼び出し
    llm_analysis = ""
    try:
        llm_analysis = await _call_llm_gateway(user_prompt, system_prompt)
    except Exception as llm_err:
        print(f"[LLM Gateway] Error: {llm_err}")
        traceback.print_exc()
        llm_analysis = (
            f"⚠️ LLM Gateway への接続に失敗しました: {llm_err}\n\n"
            f"---\n\n"
            f"**{request.store_type}** の {request.date} における予測誤差は "
            f"**{abs(error_val):.2f}億円** ({abs(pct_error):.1f}%) でした。\n\n"
            f"- 誤差方向: {'過小予測' if error_val > 0 else '過大予測'}\n"
            f"- 業態 RMSE: {error_context.get('store_type_rmse', 0):.2f}億円\n"
            f"- 全体パーセンタイル: 上位 {error_context.get('overall_percentile', 0):.0f}%\n"
        )

    # 信頼度スコア: 誤差の大きさで計算
    confidence = max(0.3, min(0.95, 1.0 - abs(pct_error) / 50))

    response_data: Dict[str, Any] = {
        "store_type": request.store_type,
        "date": request.date,
        "actual_sales": actual_sales,
        "predicted_sales": predicted_sales,
        "error": error_val,
        "rmse_context": error_context,
        "analysis": {
            "summary": llm_analysis,
            "factors": [],
            "market_conditions": {"description": ""},
            "vdb_reports": None,
        },
        "hypothesis": "",
        "confidence_score": confidence,
        "supporting_evidence": [],
        "recommendations": [],
    }

    yield _sse("complete", response_data)


@retail_router.post("/analyze-error")
async def analyze_error(request: ErrorAnalysisRequest):
    return StreamingResponse(
        _analyze_error_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
