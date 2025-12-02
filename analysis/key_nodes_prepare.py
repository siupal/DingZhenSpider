import os
from typing import Dict

import pandas as pd

try:
    from snownlp import SnowNLP
    _HAS_SNOW = True
except Exception:  # pragma: no cover - 运行环境缺失 snownlp 时降级
    SnowNLP = None
    _HAS_SNOW = False


def _score_text_continuous(s: str) -> float:
    """与 sentiment_baseline 中保持一致：优先使用 SnowNLP，回退到简易规则。

    返回范围约 [-1, 1] 的连续情感分数。
    """
    from sentiment_baseline import score_text  # 轻量导入，确保退路一致

    if not isinstance(s, str) or not s:
        return 0.0
    if _HAS_SNOW and SnowNLP is not None:
        try:
            p = float(SnowNLP(s).sentiments)  # 0~1
        except Exception:
            p = 0.5
        if p < 0.0:
            p = 0.0
        if p > 1.0:
            p = 1.0
        return 2.0 * p - 1.0
    return float(score_text(s))


def build_weekly_timeseries(input_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(input_csv):
        out = os.path.join(output_dir, "sentiment_timeseries_weekly.csv")
        pd.DataFrame([], columns=[
            "window", "count", "pos", "neg", "neu", "score",
            "pos_ratio", "neg_ratio", "neu_ratio",
            "z_count", "z_score", "d_count", "d_score",
        ]).to_csv(out, index=False)
        return out

    df = pd.read_csv(input_csv)
    if df.empty:
        out = os.path.join(output_dir, "sentiment_timeseries_weekly.csv")
        pd.DataFrame([], columns=[
            "window", "count", "pos", "neg", "neu", "score",
            "pos_ratio", "neg_ratio", "neu_ratio",
            "z_count", "z_score", "d_count", "d_score",
        ]).to_csv(out, index=False)
        return out

    # 按周聚合：以评论时间 ctime 为基准，转为周 period
    ts = pd.to_datetime(df["ctime"], unit="s", errors="coerce")
    df = df.assign(
        window=ts.dt.to_period("W").astype(str),
        sent_raw=df["message"].fillna("").astype(str).apply(_score_text_continuous),
    )
    df["sent_label"] = df["sent_raw"].apply(lambda v: 1 if v > 0.2 else (-1 if v < -0.2 else 0))
    df["w"] = 1 + df["like"].fillna(0).astype(int).clip(lower=0, upper=100)

    gdf = df[["window", "sent_raw", "sent_label", "w"]].groupby("window", sort=True)
    agg = gdf.apply(lambda g: pd.Series({
        "count": int(len(g)),
        "pos": int((g["sent_label"] > 0).sum()),
        "neg": int((g["sent_label"] < 0).sum()),
        "neu": int((g["sent_label"] == 0).sum()),
        "score": float((g["sent_raw"] * g["w"]).sum() / max(g["w"].sum(), 1)),
    })).reset_index()

    # 比例
    agg["count_safe"] = agg["count"].replace(0, pd.NA).astype("Float64")
    agg["pos_ratio"] = (agg["pos"] / agg["count_safe"]).fillna(0.0)
    agg["neg_ratio"] = (agg["neg"] / agg["count_safe"]).fillna(0.0)
    agg["neu_ratio"] = (agg["neu"] / agg["count_safe"]).fillna(0.0)
    agg = agg.drop(columns=["count_safe"])

    # z-score 与一阶差分，用于后续识别“异常周”
    if len(agg) >= 2:
        agg["z_count"] = (agg["count"] - agg["count"].mean()) / agg["count"].std(ddof=0)
        agg["z_score"] = (agg["score"] - agg["score"].mean()) / agg["score"].std(ddof=0)
        agg["d_count"] = agg["count"].diff().fillna(0.0)
        agg["d_score"] = agg["score"].diff().fillna(0.0)
    else:
        agg["z_count"] = 0.0
        agg["z_score"] = 0.0
        agg["d_count"] = 0.0
        agg["d_score"] = 0.0

    out = os.path.join(output_dir, "sentiment_timeseries_weekly.csv")
    agg.to_csv(out, index=False)
    return out


def main() -> None:
    input_csv = os.environ.get(
        "DZ_CLEANED_COMMENTS",
        os.path.join("analysis", "cleaned", "comments_cleaned.csv"),
    )
    output_dir = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    path = build_weekly_timeseries(input_csv, output_dir)
    print(path)


if __name__ == "__main__":
    main()
