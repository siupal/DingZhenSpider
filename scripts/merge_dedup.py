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


def parse_args():
    ap = argparse.ArgumentParser(description="Merge and deduplicate monthly CSVs from two folders.")
    ap.add_argument("--dir_a", default="data_click", help="first input dir")
    ap.add_argument("--dir_b", default="data_totalrank", help="second input dir")
    ap.add_argument("--out_dir", default="data_merged", help="output dir for merged CSVs")
    ap.add_argument("--keys", default="rpid,id,reply_id", help="comma separated keys for dedup if present")
    return ap.parse_args()


def main():
    args = parse_args()
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    merge_and_dedup(args.dir_a, args.dir_b, args.out_dir, keys)


if __name__ == "__main__":
    main()
