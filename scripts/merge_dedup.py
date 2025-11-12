import argparse
import os
import glob
import pandas as pd


def read_csv_safe(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False)
        except Exception:
            continue
    raise RuntimeError(f"failed to read csv: {path}")


def merge_and_dedup(dir_a: str, dir_b: str, out_dir: str, keys: list[str]):
    os.makedirs(out_dir, exist_ok=True)
    names = set()
    for d in (dir_a, dir_b):
        names.update(os.path.basename(p) for p in glob.glob(os.path.join(d, "*.csv")))

    for name in sorted(names):
        dfs = []
        for d in (dir_a, dir_b):
            p = os.path.join(d, name)
            if os.path.exists(p):
                try:
                    dfs.append(read_csv_safe(p))
                except Exception as e:
                    print(f"[warn] read {p} failed: {e}")
        if not dfs:
            continue

        df = pd.concat(dfs, ignore_index=True)

        # choose keys that exist in df
        use_keys = [k for k in keys if k in df.columns]
        if use_keys:
            df = df.drop_duplicates(subset=use_keys)
        else:
            text_cols = [c for c in ["content", "message", "text"] if c in df.columns]
            id_cols = [c for c in ["rpid", "id", "reply_id", "bvid", "oid", "mid", "uid"] if c in df.columns]
            subset = text_cols + id_cols
            df = df.drop_duplicates(subset=subset or None)

        out_path = os.path.join(out_dir, name)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"merged -> {out_path} rows={len(df)}")

        yield name, df


def parse_args():
    ap = argparse.ArgumentParser(description="Merge and deduplicate monthly CSVs from two folders.")
    ap.add_argument("--dir_a", default="data_click", help="first input dir")
    ap.add_argument("--dir_b", default="data_totalrank", help="second input dir")
    ap.add_argument("--out_dir", default="data_merged", help="output dir for merged CSVs")
    ap.add_argument("--keys", default="rpid,id,reply_id", help="comma separated keys for dedup if present")
    ap.add_argument("--relaxed_filter", action="store_true", help="enable relaxed keyword filtering for related content")
    ap.add_argument("--filter_out_dir", default="data_merged_relaxed", help="output dir for filtered CSVs if relaxed_filter is on")
    ap.add_argument("--filter_keywords", default="", help="comma separated keywords for relaxed filtering (optional)")
    ap.add_argument("--filter_keywords_file", default="", help="a text file with one keyword per line (# comments and empty lines allowed)")
    ap.add_argument(
        "--filter_cols",
        default="content,message,text,title,desc",
        help="comma separated text columns to search in",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    iterator = merge_and_dedup(args.dir_a, args.dir_b, args.out_dir, keys)

    if args.relaxed_filter:
        os.makedirs(args.filter_out_dir, exist_ok=True)
        kws = []
        if args.filter_keywords_file and os.path.exists(args.filter_keywords_file):
            with open(args.filter_keywords_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    kws.append(line)
        else:
            kws = [k.strip() for k in args.filter_keywords.split(",") if k.strip()]
        cols = [c.strip() for c in args.filter_cols.split(",") if c.strip()]
        for name, df in iterator:
            use_cols = [c for c in cols if c in df.columns]
            if not use_cols or not kws:
                continue
            mask = False
            for c in use_cols:
                s = df[c].astype(str).str.lower()
                for kw in kws:
                    mask = mask | s.str.contains(kw.lower(), na=False)
            dff = df[mask]
            out_path = os.path.join(args.filter_out_dir, name)
            dff.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"filtered -> {out_path} rows={len(dff)} (cols={','.join(use_cols)})")
    else:
        for _ in iterator:
            pass


if __name__ == "__main__":
    main()
