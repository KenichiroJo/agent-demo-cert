"""
VectorDatabase 検索モジュール
DataRobot VDB デプロイメント (DRUM prediction server) を使って関連ドキュメントを検索する

リクエスト形式: CSV (promptText カラム)
  → MCP tool document_tools.py と同じパターン
"""

import csv
import io
import json
import os
from typing import List

import httpx


async def search_vdb(
    query: str,
    deployment_id: str,
    max_results: int = 3,
) -> List[str]:
    """
    DataRobot VDB デプロイメントに対してクエリを実行し、
    関連するドキュメントのテキストを返す。

    Parameters
    ----------
    query : str
        検索クエリ文字列
    deployment_id : str
        DataRobot VDB デプロイメント ID
    max_results : int
        返却する最大結果数

    Returns
    -------
    List[str]
        関連ドキュメントのテキストリスト
    """
    endpoint = os.getenv("DATAROBOT_ENDPOINT", "").rstrip("/")
    token = os.getenv("DATAROBOT_API_TOKEN", "")

    if not endpoint or not token or not deployment_id:
        return []

    # VDB デプロイメントの予測エンドポイント
    base = endpoint.rstrip("/")
    if base.endswith("/api/v2"):
        base = base[: -len("/api/v2")]
    predict_url = f"{base}/api/v2/deployments/{deployment_id}/predictions"

    # DRUM prediction server は CSV 形式を期待する
    # MCP tool の document_tools.py と同じパターン: promptText カラム
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "text/csv; encoding=utf-8",
        "Accept": "application/json",
    }

    # CSV ボディ構築 (クエリ内の改行・カンマ・引用符をエスケープ)
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["promptText"])
    writer.writerow([query])
    csv_body = csv_buf.getvalue()

    print(f"[VDB] Sending request to {predict_url}, query='{query[:60]}...'")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.post(
            predict_url,
            content=csv_body.encode("utf-8"),
            headers=headers,
        )
        resp.raise_for_status()

    # レスポンスパース: JSON or CSV
    results: List[str] = []
    content_type = resp.headers.get("content-type", "")
    raw_text = resp.text[:500]
    print(f"[VDB] Response content-type={content_type}, body_preview={raw_text[:300]}")

    if "application/json" in content_type:
        data = resp.json()
        results = _parse_json_response(data, max_results)
    else:
        # CSV or text レスポンス
        results = _parse_text_response(resp.text, max_results)

    print(f"[VDB] Response: {len(results)} documents extracted")
    return results[:max_results]


def _parse_json_response(data: object, max_results: int) -> List[str]:
    """JSON レスポンスからドキュメントテキストを抽出"""
    results: List[str] = []

    if isinstance(data, dict):
        # DRUM 予測レスポンス: {"data": [...]} or {"predictions": [...]}
        rows = data.get("data", data.get("predictions", data.get("documents", [])))
        if isinstance(rows, list):
            for row in rows[:max_results]:
                text = _extract_text_from_record(row)
                if text:
                    results.append(text)
        # 単一レコードの場合
        if not results:
            text = _extract_text_from_record(data)
            if text:
                results.append(text)

    elif isinstance(data, list):
        for item in data[:max_results]:
            text = _extract_text_from_record(item)
            if text:
                results.append(text)

    return results


def _extract_text_from_record(record: object) -> str:
    """レコード（dict or str）からテキストを抽出"""
    if isinstance(record, str):
        return record.strip() if record.strip() else ""

    if isinstance(record, dict):
        # メタデータからソース情報を取得
        source = ""
        metadata = record.get("metadata")
        if isinstance(metadata, dict):
            source = metadata.get("source", "")

        # 優先順: resultText > text > content > page_content > prediction
        for key in ["resultText", "text", "content", "page_content", "prediction"]:
            val = record.get(key)
            if not val:
                continue

            # リスト型の場合（VDB prediction レスポンス: ["text1", "text2", ...]）
            if isinstance(val, list):
                texts = [str(v).strip() for v in val if v and str(v).strip()]
                if texts:
                    combined = "\n\n".join(texts)
                    if source:
                        return f"[出典: {source}]\n{combined}"
                    return combined
                continue

            if isinstance(val, str) and val.strip():
                if source:
                    return f"[出典: {source}]\n{val.strip()}"
                return val.strip()

        # 全カラムをチェック — 長いテキストフィールドを探す
        for key, val in record.items():
            if isinstance(val, str) and len(val) > 50:
                return val.strip()
            # リスト内の長いテキストも対象
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and len(item) > 50:
                        return item.strip()

    return ""


def _parse_text_response(text: str, max_results: int) -> List[str]:
    """CSV/テキスト レスポンスからドキュメントテキストを抽出"""
    results: List[str] = []

    # まず JSON としてパースを試みる
    try:
        data = json.loads(text)
        return _parse_json_response(data, max_results)
    except (json.JSONDecodeError, ValueError):
        pass

    # CSV としてパース
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            for key in ["resultText", "text", "content", "page_content", "prediction"]:
                val = row.get(key, "")
                if val and val.strip():
                    results.append(val.strip())
                    break
            else:
                # 最も長いフィールドを使う
                vals = [v for v in row.values() if v and isinstance(v, str)]
                if vals:
                    longest = max(vals, key=len)
                    if len(longest) > 50:
                        results.append(longest.strip())

            if len(results) >= max_results:
                break
    except Exception:
        # 最終フォールバック: テキストそのまま
        if text.strip():
            results.append(text.strip()[:2000])

    return results
