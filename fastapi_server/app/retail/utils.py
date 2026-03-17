"""
ユーティリティモジュール
JSON シリアライズ時の NaN/Inf 値を安全に変換する関数群
"""

import math
from typing import Any, Optional

import numpy as np


def clean_nan_values(obj: Any) -> Any:
    """再帰的に NaN/inf 値を None に置換し、JSON シリアライズを安全にする。"""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    # Python float と numpy floating 型の両方を処理
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    return obj


def json_safe_float(value: Any) -> Optional[float]:
    """
    スカラー値を JSON 安全な float に変換する。

    欠損値 (NaN/pd.NA/None) や非有限値 (inf/-inf) の場合は None を返す。
    """
    if value is None:
        return None

    # pandas が利用可能な場合のみインポート
    try:
        import pandas as pd  # type: ignore

        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        v = float(value)
    except Exception:
        return None

    if math.isnan(v) or math.isinf(v):
        return None
    return v
