import os
import math
import pandas as pd
try:
    from snownlp import SnowNLP
    _HAS_SNOW = True
except Exception:
    SnowNLP = None
    _HAS_SNOW = False

_pos = set(["爱","喜欢","支持","牛","真棒","厉害","太好","优秀","好看","帅","哈哈","笑死"])
_neg = set(["坏","讨厌","垃圾","无语","恶心","黑","喷","离谱","难看","气死","翻白眼"])
_pos_emoji = set(["😀","😁","😂","🤣","😊","😍","👍","❤","😻","😄"]) 
_neg_emoji = set(["😡","🤬","😞","😢","😭","👎","💔","🙄","😒"]) 


def score_text(s: str) -> int:
    if not isinstance(s, str) or not s:
        return 0
    p = 0
    n = 0
    for w in _pos:
        if w in s:
            p += 1
    for w in _neg:
        if w in s:
            n += 1
    for e in _pos_emoji:
        if e in s:
            p += 1
    for e in _neg_emoji:
        if e in s:
            n += 1
    if p > n:
        return 1
    if n > p:
        return -1
    return 0


def _score_text_continuous(s: str) -> float:
    if not isinstance(s, str) or not s:
        return 0.0
    if _HAS_SNOW and SnowNLP is not None:
        try:
            p = float(SnowNLP(s).sentiments)
        except Exception:
            p = 0.5
        if p < 0.0:
            p = 0.0
        if p > 1.0:
            p = 1.0
        return 2.0 * p - 1.0
    return float(score_text(s))


def run(input_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(input_csv):
        out = os.path.join(output_dir, "sentiment_timeseries.csv")
        pd.DataFrame([], columns=["window","count","pos","neg","neu","score","pos_ratio","neg_ratio","neu_ratio"]).to_csv(out, index=False)
        return out
    df = pd.read_csv(input_csv)
    if df.empty:
        out = os.path.join(output_dir, "sentiment_timeseries.csv")
        pd.DataFrame([], columns=["window","count","pos","neg","neu","score","pos_ratio","neg_ratio","neu_ratio"]).to_csv(out, index=False)
        return out
    df["window"] = pd.to_datetime(df["ctime"], unit="s", errors="coerce").dt.to_period("M").astype(str)
    df["sent_raw"] = df["message"].fillna("").astype(str).apply(_score_text_continuous)
    df["sent_label"] = df["sent_raw"].apply(lambda v: 1 if v > 0.2 else (-1 if v < -0.2 else 0))
    df["w"] = 1 + df["like"].fillna(0).astype(int).clip(lower=0, upper=100)

    # 仅对真正需要的列做聚合，避免 pandas FutureWarning
    gdf = df[["window", "sent_raw", "sent_label", "w"]].groupby("window", sort=True)
    agg = gdf.apply(lambda g: pd.Series({
        "count": int(len(g)),
        "pos": int((g["sent_label"] > 0).sum()),
        "neg": int((g["sent_label"] < 0).sum()),
        "neu": int((g["sent_label"] == 0).sum()),
        "score": float((g["sent_raw"] * g["w"]).sum() / max(g["w"].sum(), 1)),
    })).reset_index()

    # 比例指标：更稳定比较不同月份情感结构
    agg["count_safe"] = agg["count"].replace(0, pd.NA).astype("Float64")
    agg["pos_ratio"] = (agg["pos"] / agg["count_safe"]).fillna(0.0)
    agg["neg_ratio"] = (agg["neg"] / agg["count_safe"]).fillna(0.0)
    agg["neu_ratio"] = (agg["neu"] / agg["count_safe"]).fillna(0.0)
    agg = agg.drop(columns=["count_safe"])
    out = os.path.join(output_dir, "sentiment_timeseries.csv")
    agg.to_csv(out, index=False)
    return out


def main():
    input_csv = os.environ.get("DZ_CLEANED_COMMENTS", os.path.join("analysis","cleaned","comments_cleaned.csv"))
    output_dir = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    path = run(input_csv, output_dir)
    print(path)


if __name__ == "__main__":
    main()
