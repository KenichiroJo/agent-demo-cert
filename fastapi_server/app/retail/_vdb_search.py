"""
VectorDatabase 検索モジュール
DataRobot VDB デプロイメントを使って関連ドキュメントを検索する
"""

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

    headers = {
        "Authorization": f"Token {token}",
        "x-datarobot-api-token": token,
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "maxDocuments": max_results,
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.post(predict_url, json=payload, headers=headers)
        resp.raise_for_status()

    data = resp.json()
    results: List[str] = []

    # DataRobot VDB レスポンス形式に応じて結果を抽出
    if isinstance(data, dict):
        # 標準的な VDB レスポンス形式
        for doc in data.get("data", data.get("documents", [])):
            if isinstance(doc, dict):
                text = doc.get("text", doc.get("content", doc.get("page_content", "")))
                if text:
                    # メタデータがあればソース情報を付加
                    source = doc.get("metadata", {}).get("source", "")
                    if source:
                        results.append(f"[出典: {source}]\n{text}")
                    else:
                        results.append(text)
            elif isinstance(doc, str):
                results.append(doc)
    elif isinstance(data, list):
        for item in data[:max_results]:
            if isinstance(item, dict):
                text = item.get("text", item.get("content", ""))
                if text:
                    results.append(text)
            elif isinstance(item, str):
                results.append(item)

    return results[:max_results]
