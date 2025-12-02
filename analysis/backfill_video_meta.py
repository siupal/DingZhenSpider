import os
import time
from typing import Dict, Any

import pandas as pd
import requests


API_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"


def fetch_video_meta(bvid: str, timeout: float = 10.0) -> Dict[str, Any]:
    """调用 B 站公开接口按 bvid 获取视频元数据。

    返回尽量精简且与 key_videos 列兼容的字段。
    """
    try:
        resp = requests.get(API_VIEW_URL, params={"bvid": bvid}, timeout=timeout)
        resp.raise_for_status()
        j = resp.json()
    except Exception:
        return {}

    if not isinstance(j, dict) or j.get("code") not in (0, "0"):
        return {}

    data = j.get("data") or {}
    stat = data.get("stat") or {}

    return {
        "title": data.get("title"),
        "view": stat.get("view"),
        "reply": stat.get("reply"),
        "like": stat.get("like"),
    }


def backfill_key_videos(input_csv: str, output_csv: str, sleep_between: float = 0.6) -> str:
    if not os.path.exists(input_csv):
        raise FileNotFoundError(input_csv)
    df = pd.read_csv(input_csv)
    if df.empty:
        df.to_csv(output_csv, index=False)
        return output_csv

    # 需要补全的行：标题为空或 view 为空
    need_mask = df["title"].isna() | (df["title"].astype(str).str.len() == 0) | df["view"].isna()
    need = df[need_mask].copy()
    if need.empty:
        # 没有需要补全的，直接复制一份 enriched
        df.to_csv(output_csv, index=False)
        return output_csv

    bvids = sorted(set(need["bvid"].dropna().astype(str)))
    meta_cache: Dict[str, Dict[str, Any]] = {}

    for i, bvid in enumerate(bvids, start=1):
        m = fetch_video_meta(bvid)
        meta_cache[bvid] = m
        # 简单限速，避免对接口压力太大
        time.sleep(sleep_between)

    # 将拉到的元数据写回 DataFrame
    for bvid, meta in meta_cache.items():
        if not meta:
            continue
        mask = df["bvid"].astype(str) == bvid
        for col in ("title", "view", "reply", "like"):
            if col not in df.columns:
                continue
            # 只在原值缺失时填充
            missing = df.loc[mask, col].isna()
            if missing.any():
                df.loc[mask & missing, col] = meta.get(col)

    df.to_csv(output_csv, index=False)
    return output_csv


def main() -> None:
    base_analysis = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    in_csv = os.path.join(base_analysis, "key_videos.csv")
    out_csv = os.path.join(base_analysis, "key_videos_enriched.csv")
    path = backfill_key_videos(in_csv, out_csv)
    print(path)


if __name__ == "__main__":
    main()
