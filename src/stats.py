from __future__ import annotations
import os
from typing import Dict

import pandas as pd


def generate_stats(csv_path: str, output_dir: str) -> Dict[str, str]:
    if not os.path.exists(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    # 保障字段存在
    num = len(df)
    totals = {
        "count": num,
        "view_sum": int(df.get("view", pd.Series([0]*num)).sum()),
        "like_sum": int(df.get("like", pd.Series([0]*num)).sum()),
        "danmaku_sum": int(df.get("danmaku", pd.Series([0]*num)).sum()),
        "reply_sum": int(df.get("reply", pd.Series([0]*num)).sum()),
        "favorite_sum": int(df.get("favorite", pd.Series([0]*num)).sum()),
        "coin_sum": int(df.get("coin", pd.Series([0]*num)).sum()),
        "share_sum": int(df.get("share", pd.Series([0]*num)).sum()),
    }

    # summary.csv（单行汇总）
    summary_csv = os.path.join(output_dir, "summary.csv")
    pd.DataFrame([totals]).to_csv(summary_csv, index=False)

    # TopN（view与like，各取前20）
    top_view_csv = os.path.join(output_dir, "top_view.csv")
    top_like_csv = os.path.join(output_dir, "top_like.csv")
    if "view" in df.columns:
        df.sort_values(by=["view", "like"], ascending=[False, False]).head(20).to_csv(top_view_csv, index=False)
    if "like" in df.columns:
        df.sort_values(by=["like", "view"], ascending=[False, False]).head(20).to_csv(top_like_csv, index=False)

    return {"summary": summary_csv, "top_view": top_view_csv, "top_like": top_like_csv}
