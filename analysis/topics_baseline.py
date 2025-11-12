import os
import re
import pandas as pd
import jieba

_stop = set(["的","了","啊","么","吗","呀","哦","和","与","及","也","很","在","就","都","还","又","而且","但是","如果","就是","这个","那个","一个","不是","没有"]) 
_token_re = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")


def tokenize(s: str):
    if not isinstance(s, str):
        return []
    s = "".join(_token_re.findall(s))
    ws = jieba.lcut(s)
    return [w for w in ws if w and w not in _stop and len(w)>=2]


def run(input_csv: str, output_dir: str, topn: int = 50) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.exists(input_csv):
        out = os.path.join(output_dir, "topics_by_window.csv")
        pd.DataFrame([], columns=["window","word","freq"]).to_csv(out, index=False)
        return out
    df = pd.read_csv(input_csv)
    if df.empty:
        out = os.path.join(output_dir, "topics_by_window.csv")
        pd.DataFrame([], columns=["window","word","freq"]).to_csv(out, index=False)
        return out
    df["window"] = pd.to_datetime(df["ctime"], unit="s", errors="coerce").dt.to_period("M").astype(str)
    df["tokens"] = df["message"].fillna("").astype(str).apply(tokenize)
    recs = []
    for w, g in df.explode("tokens").groupby(["window","tokens"], as_index=False):
        pass
    gdf = df.explode("tokens").groupby(["window","tokens"]).size().reset_index(name="freq")
    gdf = gdf.sort_values(["window","freq"], ascending=[True, False])
    out_rows = []
    for window, sub in gdf.groupby("window"):
        head = sub.head(topn)
        for _, r in head.iterrows():
            out_rows.append({"window": window, "word": r["tokens"], "freq": int(r["freq"])})
    out = os.path.join(output_dir, "topics_by_window.csv")
    pd.DataFrame(out_rows).to_csv(out, index=False)
    return out


def main():
    input_csv = os.environ.get("DZ_CLEANED_COMMENTS", os.path.join("analysis","cleaned","comments_cleaned.csv"))
    output_dir = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis"))
    path = run(input_csv, output_dir)
    print(path)


if __name__ == "__main__":
    main()
