import os
import re
import pandas as pd
from typing import List, Dict

PAT_ERR = re.compile(r"^comments_(.+)_(\d{6})_errors\.csv$")


def scan_errors(data_dir: str) -> List[Dict[str, str]]:
    rows = []
    for fn in os.listdir(data_dir):
        m = PAT_ERR.match(fn)
        if not m:
            continue
        kw = m.group(1)
        ym = m.group(2)
        rows.append({"keyword": kw, "ym": ym, "error_csv": os.path.join(data_dir, fn)})
    return sorted(rows, key=lambda x: x["ym"])  # chronological


def month_detail(data_dir: str, kw: str, ym: str, err_csv: str) -> pd.DataFrame:
    # expected monthly video list CSV
    base = f"comments_{kw}_{ym}"
    vid_csv = os.path.join(data_dir, f"{base}.csv")
    # read error list
    err = pd.read_csv(err_csv)
    if os.path.exists(vid_csv):
        vids = pd.read_csv(vid_csv)
    else:
        vids = pd.DataFrame()
    # join by bvid if possible
    if not vids.empty and "bvid" in vids.columns:
        df = err.merge(vids, how="left", on="bvid", suffixes=("", ""))
    else:
        df = err
    # sort by view if available
    if "view" in df.columns:
        df = df.sort_values(by=["view"], ascending=[False])
    return df


def run(data_dir: str, output_dir: str) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    items = scan_errors(data_dir)
    if not items:
        # still write empty summary for consistency
        out_sum = os.path.join(output_dir, "closed_comments_summary.csv")
        pd.DataFrame([], columns=["ym","keyword","count","view_sum"]).to_csv(out_sum, index=False)
        return {"summary": out_sum}

    out_detail_dir = os.path.join(output_dir, "closed_comments")
    os.makedirs(out_detail_dir, exist_ok=True)

    sum_rows = []
    for it in items:
        kw, ym, err_csv = it["keyword"], it["ym"], it["error_csv"]
        try:
            df = month_detail(data_dir, kw, ym, err_csv)
        except Exception:
            continue
        out_month = os.path.join(out_detail_dir, f"{ym}_closed.csv")
        try:
            df.to_csv(out_month, index=False)
        except Exception:
            pass
        cnt = int(len(df))
        vsum = int(df.get("view", pd.Series([0]*cnt)).sum()) if cnt>0 else 0
        sum_rows.append({"ym": ym, "keyword": kw, "count": cnt, "view_sum": vsum})

    sum_df = pd.DataFrame(sum_rows).sort_values(["ym", "keyword"]) if sum_rows else pd.DataFrame([])
    out_sum = os.path.join(output_dir, "closed_comments_summary.csv")
    sum_df.to_csv(out_sum, index=False)
    return {"summary": out_sum, "detail_dir": out_detail_dir}


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", default="data")
    p.add_argument("--analysis_dir", default="analysis")
    args = p.parse_args()
    run(args.data_dir, args.analysis_dir)


if __name__ == "__main__":
    main()
