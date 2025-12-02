import os
import pandas as pd


def detect_candidate_weeks(weekly_csv: str, output_dir: str, count_min: int = 20) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(weekly_csv):
        out = os.path.join(output_dir, "candidate_weeks.csv")
        pd.DataFrame([], columns=[
            "window", "count", "score",
            "pos_ratio", "neg_ratio", "neu_ratio",
            "z_count", "z_score", "d_count", "d_score",
            "is_score_peak", "is_count_peak", "is_turning",
        ]).to_csv(out, index=False)
        return out

    df = pd.read_csv(weekly_csv)
    if df.empty:
        out = os.path.join(output_dir, "candidate_weeks.csv")
        pd.DataFrame([], columns=[
            "window", "count", "score",
            "pos_ratio", "neg_ratio", "neu_ratio",
            "z_count", "z_score", "d_count", "d_score",
            "is_score_peak", "is_count_peak", "is_turning",
        ]).to_csv(out, index=False)
        return out

    # 只保留样本量足够的周
    df = df[df["count"] >= count_min].reset_index(drop=True)
    if df.empty:
        out = os.path.join(output_dir, "candidate_weeks.csv")
        pd.DataFrame([], columns=[
            "window", "count", "score",
            "pos_ratio", "neg_ratio", "neu_ratio",
            "z_count", "z_score", "d_count", "d_score",
            "is_score_peak", "is_count_peak", "is_turning",
        ]).to_csv(out, index=False)
        return out

    # 若尚未有 z/d 列，则根据当前 df 再算一遍（兼容性考虑）
    if "z_count" not in df.columns or "z_score" not in df.columns:
        if len(df) >= 2:
            df["z_count"] = (df["count"] - df["count"].mean()) / df["count"].std(ddof=0)
            df["z_score"] = (df["score"] - df["score"].mean()) / df["score"].std(ddof=0)
            df["d_count"] = df["count"].diff().fillna(0.0)
            df["d_score"] = df["score"].diff().fillna(0.0)
        else:
            df["z_count"] = 0.0
            df["z_score"] = 0.0
            df["d_count"] = 0.0
            df["d_score"] = 0.0

    # 情绪强度异常、评论量异常、情绪变化剧烈
    # 阈值可以以后按需要调整
    df["is_score_peak"] = df["z_score"].abs() >= 1.5
    df["is_count_peak"] = df["z_count"] >= 1.5

    # 用分位数定义“转折”：d_score 绝对值排在整体的后 10%
    if "d_score" in df.columns and not df["d_score"].isna().all():
        q_d = df["d_score"].abs().quantile(0.9)
        df["is_turning"] = df["d_score"].abs() >= q_d
    else:
        df["is_turning"] = False

    df["is_candidate"] = df[["is_score_peak", "is_count_peak", "is_turning"]].any(axis=1)
    cand = df[df["is_candidate"]].copy()

    cols = [
        "window", "count", "score",
        "pos_ratio", "neg_ratio", "neu_ratio",
        "z_count", "z_score", "d_count", "d_score",
        "is_score_peak", "is_count_peak", "is_turning",
    ]
    cand = cand.reindex(columns=cols)

    out = os.path.join(output_dir, "candidate_weeks.csv")
    cand.to_csv(out, index=False)
    return out


def main() -> None:
    weekly_csv = os.environ.get(
        "DZ_WEEKLY_TS",
        os.path.join("analysis", "sentiment_timeseries_weekly.csv"),
    )
    output_dir = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    path = detect_candidate_weeks(weekly_csv, output_dir, count_min=20)
    print(path)


if __name__ == "__main__":
    main()
