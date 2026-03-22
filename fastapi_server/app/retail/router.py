"""
小売売上予測ダッシュボード API ルーター
リファレンス: forecast-agent-main/backend/routers/ercot_api.py
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.retail.analysis import analyze_retail_forecast_error
from app.retail.chat import stream_chat_with_retail_assistant
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


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    store_type: str | None = None


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


def _build_surrounding_context(dp: RetailDataProcessor, store_type: str) -> str:
    """同業態の直近売上推移データを整形して返す"""
    df = dp.get_merged_data()
    df_st = df[(df["store_type"] == store_type) & (df["predicted_sales"].notna())].copy()
    df_st = df_st.sort_values("year_month")

    rows = []
    for _, r in df_st.iterrows():
        dt = r["year_month"]
        dt_str = dt.strftime("%Y-%m") if hasattr(dt, "strftime") else str(dt)[:7]
        actual = r.get("sales_billion_yen")
        pred = r.get("predicted_sales")
        err = r.get("forecast_error")
        pct = r.get("pct_error")
        if all(v is not None and v == v for v in [actual, pred, err, pct]):
            rows.append(
                f"  {dt_str}: 実績={actual:.2f}億円, 予測={pred:.2f}億円, "
                f"誤差={err:+.3f}億円 ({pct:+.1f}%)"
            )
        else:
            rows.append(f"  {dt_str}: データ不完全")

    return "\n".join(rows[-18:])  # 最新18ヶ月まで


async def _analyze_error_stream(request: ErrorAnalysisRequest):
    """
    SSE ストリームで誤差分析を返す
    パターン: forecast-agent-main/backend/routers/ercot_api.py の _analyze_error_stream と同じ
    - asyncio.create_task で LLM 呼び出しを非同期実行
    - 10秒ごとに heartbeat を送信
    - 完了時に complete イベントを送信
    """
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

    # 周辺時系列データ取得
    surrounding = _build_surrounding_context(_dp(), request.store_type)

    # LLM 分析を asyncio.create_task で非同期実行 (ERCOT パターン)
    analysis_task = asyncio.create_task(
        analyze_retail_forecast_error(
            data_point=data_point,
            error_context=error_context,
            surrounding_data=surrounding,
        )
    )

    # heartbeat ループ (ERCOT パターン: 10秒ごと)
    elapsed = 0
    while not analysis_task.done():
        await asyncio.sleep(10)
        elapsed += 10
        if not analysis_task.done():
            yield _sse("heartbeat", {"status": "processing", "elapsed": elapsed})

    try:
        analysis_result = await analysis_task
    except Exception as e:
        yield _sse("error", {"error": f"分析に失敗しました: {str(e)}"})
        return

    analysis_result = clean_nan_values(analysis_result)
    error_context = clean_nan_values(error_context)

    actual_sales = float(data_point.get("sales_billion_yen", 0) or 0)
    predicted_sales = float(data_point.get("predicted_sales", 0) or 0)
    error_val = float(data_point.get("forecast_error", 0) or 0)

    response_data: Dict[str, Any] = {
        "store_type": request.store_type,
        "date": request.date,
        "actual_sales": actual_sales,
        "predicted_sales": predicted_sales,
        "error": error_val,
        "rmse_context": error_context,
        "analysis": analysis_result.get("analysis", {}),
        "hypothesis": analysis_result.get("hypothesis", ""),
        "confidence_score": float(analysis_result.get("confidence_score", 0.0) or 0.0),
        "supporting_evidence": analysis_result.get("supporting_evidence", []),
        "recommendations": analysis_result.get("recommendations", []),
    }

    yield _sse("complete", response_data)


@retail_router.post("/analyze-error")
async def analyze_error(request: ErrorAnalysisRequest):
    return StreamingResponse(
        _analyze_error_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# AI チャットエンドポイント (SSE ストリーミング)
# ---------------------------------------------------------------------------

@retail_router.post("/chat")
async def retail_chat(request: ChatRequest):
    """
    対話形式で売上データを分析するチャットエンドポイント
    SSE ストリーミングで LLM レスポンスをリアルタイム返却
    """
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    return StreamingResponse(
        stream_chat_with_retail_assistant(messages=messages, dp=_dp(), store_type=request.store_type),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
