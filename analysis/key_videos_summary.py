import os
from typing import List

import pandas as pd


def summarize_key_videos(key_videos_csv: str, output_csv: str) -> str:
    if not os.path.exists(key_videos_csv):
        raise FileNotFoundError(key_videos_csv)
    df = pd.read_csv(key_videos_csv)
    if df.empty:
        # 直接输出空表
        pd.DataFrame([], columns=[
            "bvid", "title", "view_max", "reply_max", "like_max",
            "first_window", "last_window", "n_windows",
            "importance_max", "importance_sum",
            "sent_mean_mean", "sent_mean_std",
        ]).to_csv(output_csv, index=False)
        return output_csv

    df["window"] = df["window"].astype(str)

    def _agg_windows(ws: pd.Series) -> pd.Series:
        uniq = sorted(set(ws))
        return pd.Series({
            "first_window": uniq[0],
            "last_window": uniq[-1],
            "n_windows": len(uniq),
            "windows_joined": ";".join(uniq),
        })

    grouped = df.groupby("bvid")

    meta = grouped.apply(lambda g: pd.Series({
        "title": g["title"].dropna().astype(str).iloc[0] if g["title"].notna().any() else "",
        "view_max": g["view"].max(skipna=True),
        "reply_max": g["reply"].max(skipna=True),
        "like_max": g["like"].max(skipna=True),
        "importance_max": g["importance"].max(skipna=True),
        "importance_sum": g["importance"].sum(skipna=True),
        "sent_mean_mean": g["sent_mean"].mean(skipna=True),
        "sent_mean_std": g["sent_mean"].std(ddof=0, skipna=True),
    }))

    win_info = grouped["window"].apply(_agg_windows)

    out = meta.join(win_info)
    out = out.reset_index()  # bvid 变成列

    # 调整列顺序
    cols: List[str] = [
        "bvid", "title",
        "view_max", "reply_max", "like_max",
        "first_window", "last_window", "n_windows", "windows_joined",
        "importance_max", "importance_sum",
        "sent_mean_mean", "sent_mean_std",
    ]
    out = out.reindex(columns=cols)
    out.to_csv(output_csv, index=False)
    return output_csv


def main() -> None:
    base_analysis = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    in_csv = os.path.join(base_analysis, "key_videos.csv")
    out_csv = os.path.join(base_analysis, "key_videos_summary.csv")
    path = summarize_key_videos(in_csv, out_csv)
    print(path)


if __name__ == "__main__":
    main()
