import os
import math
import pandas as pd

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


def run(input_csv: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(input_csv):
        out = os.path.join(output_dir, "sentiment_timeseries.csv")
        pd.DataFrame([], columns=["window","count","pos","neg","neu","score"]).to_csv(out, index=False)
        return out
    df = pd.read_csv(input_csv)
    if df.empty:
        out = os.path.join(output_dir, "sentiment_timeseries.csv")
        pd.DataFrame([], columns=["window","count","pos","neg","neu","score"]).to_csv(out, index=False)
        return out
    df["window"] = pd.to_datetime(df["ctime"], unit="s", errors="coerce").dt.to_period("M").astype(str)
    df["sent"] = df["message"].fillna("").astype(str).apply(score_text)
    df["w"] = 1 + df["like"].fillna(0).astype(int).clip(lower=0, upper=100)
    agg = df.groupby("window").apply(lambda g: pd.Series({
        "count": int(len(g)),
        "pos": int((g["sent"]>0).sum()),
        "neg": int((g["sent"]<0).sum()),
        "neu": int((g["sent"]==0).sum()),
        "score": float((g["sent"]*g["w"]).sum() / max(g["w"].sum(),1))
    })).reset_index()
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
