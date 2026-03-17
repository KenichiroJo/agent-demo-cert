"""
小売需要予測ダッシュボード API ルーター
リファレンス: forecast-agent-main/backend/routers/ercot_api.py
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Dict, Optional

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


@retail_router.get("/retail/api/store-types")
async def get_store_types():
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    return {"status": "success", "store_types": _dp().get_store_types()}


@retail_router.get("/retail/api/status")
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


@retail_router.get("/retail/api/date-range")
async def get_date_range():
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    dr = _dp().get_date_range()
    return {"status": "success", "start_date": dr["start"], "end_date": dr["end"]}


@retail_router.get("/retail/api/forecast-data")
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


@retail_router.get("/retail/api/error-metrics")
async def get_error_metrics(store_type: Optional[str] = None):
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    metrics = _ea().calculate_metrics(_dp().get_merged_data(), store_type=store_type)
    return clean_nan_values({"status": "success", "metrics": metrics})


@retail_router.get("/retail/api/outliers")
async def get_outliers(store_type: Optional[str] = None, threshold: float = 2.0, limit: int = 100):
    try:
        _ensure_initialized()
    except Exception:
        raise HTTPException(status_code=503, detail=f"Not initialized: {_init_error}")
    outliers = _ea().detect_outliers(_dp().get_merged_data(), store_type=store_type, threshold=threshold, limit=limit)
    return clean_nan_values({"status": "success", "threshold": threshold, "count": len(outliers), "outliers": outliers})


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

    vdb_reports: list[str] = []
    vdb_deployment_id = os.getenv("VDB_DEPLOYMENT_ID", "")
    if vdb_deployment_id:
        try:
            from app.retail._vdb_search import search_vdb
            vdb_reports = await search_vdb(
                query=f"{request.store_type} 売上予測 誤差要因 {request.date}",
                deployment_id=vdb_deployment_id,
            )
        except Exception as vdb_err:
            print(f"VDB search failed: {vdb_err}")

    yield _sse("heartbeat", {"status": "processing", "elapsed": 5})

    actual_sales = float(data_point.get("sales_billion_yen", 0) or 0)
    predicted_sales = float(data_point.get("predicted_sales", 0) or 0)
    error_val = float(data_point.get("forecast_error", 0) or 0)
    error_context = clean_nan_values(error_context)

    response_data: Dict[str, Any] = {
        "store_type": request.store_type,
        "date": request.date,
        "actual_sales": actual_sales,
        "predicted_sales": predicted_sales,
        "error": error_val,
        "rmse_context": error_context,
        "analysis": {
            "summary": (
                f"**{request.store_type}** の {request.date} における予測誤差は "
                f"**{abs(error_val):.1f}億円** "
                f"({'過大予測' if error_val < 0 else '過小予測'}) でした。\n\n"
                f"この業態の平均 RMSE は {error_context.get('store_type_rmse', 0):.1f}億円、"
                f"MAE は {error_context.get('store_type_mae', 0):.1f}億円 です。\n\n"
                f"全体パーセンタイル: 上位 {error_context.get('overall_percentile', 0):.0f}% に位置します。"
            ),
            "factors": [],
            "market_conditions": {"description": "詳細な市場条件分析にはエージェントチャットをご利用ください。"},
            "vdb_reports": vdb_reports if vdb_reports else None,
        },
        "hypothesis": f"{request.store_type}の{request.date}の売上が予測と乖離した要因として、季節変動、消費者動向の変化、または外部経済要因が考えられます。",
        "confidence_score": 0.7,
        "supporting_evidence": [],
        "recommendations": [
            "AIアシスタントタブで詳細なエラー分析を依頼してください",
            "類似の業態・期間での誤差傾向を確認してください",
        ],
    }

    yield _sse("complete", response_data)


@retail_router.post("/retail/api/analyze-error")
async def analyze_error(request: ErrorAnalysisRequest):
    return StreamingResponse(
        _analyze_error_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
