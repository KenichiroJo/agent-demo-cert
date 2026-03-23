"""
DataRobot ランタイムパラメータ読み取りユーティリティ

デプロイ環境では環境変数が MLOPS_RUNTIME_PARAM_{KEY} に JSON ペイロード形式で設定される。
ローカル開発環境では通常の環境変数として設定される。
このモジュールは両方に対応する。

パターン: forecast-agent-main/backend/config.py の get_runtime_param() と同じ
"""

import json
import os


def get_runtime_param(env_name: str, default: str = "") -> str:
    """
    DataRobot ランタイムパラメータを取得する

    優先順位:
    1. MLOPS_RUNTIME_PARAM_{env_name} (デプロイ環境のJSON形式)
    2. {env_name} (ローカル開発環境の通常環境変数)
    3. default

    JSON ペイロード形式:
    - string: {"type":"string","payload":"the-value"}
    - credential: {"type":"credential","payload":{"credentialType":"api_token","apiToken":"..."}}
    """
    # デプロイ環境: MLOPS_RUNTIME_PARAM_ プレフィックス付き
    runtime_param = os.getenv(f"MLOPS_RUNTIME_PARAM_{env_name}")
    if runtime_param:
        try:
            parsed = json.loads(runtime_param)
            if isinstance(parsed, dict):
                payload = parsed.get("payload")
                if isinstance(payload, dict):
                    # credential 型
                    return payload.get("apiToken", payload.get("value", str(payload)))
                if payload is not None:
                    return str(payload)
            return str(parsed)
        except (json.JSONDecodeError, ValueError):
            return runtime_param

    # ローカル開発環境: 通常の環境変数
    return os.getenv(env_name, default)
