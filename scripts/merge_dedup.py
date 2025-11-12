import argparse
import os
import glob
import pandas as pd
import shutil
import json


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


def choose_and_copy_json(month_csv_name: str, dir_a: str, dir_b: str, json_out_dir: str):
    base = os.path.splitext(month_csv_name)[0] + ".json"
    pa = os.path.join(dir_a, base)
    pb = os.path.join(dir_b, base)
    cand = []
    if os.path.exists(pa):
        try:
            cand.append((pa, os.path.getsize(pa)))
        except Exception:
            cand.append((pa, 0))
    if os.path.exists(pb):
        try:
            cand.append((pb, os.path.getsize(pb)))
        except Exception:
            cand.append((pb, 0))
    if not cand:
        return False, None
    cand.sort(key=lambda x: x[1], reverse=True)
    src = cand[0][0]
    os.makedirs(json_out_dir, exist_ok=True)
    dst = os.path.join(json_out_dir, base)
    try:
        shutil.copy2(src, dst)
        print(f"json -> {dst} from {src} size={cand[0][1]}")
        return True, dst
    except Exception as e:
        print(f"[warn] copy json failed for {base}: {e}")
        return False, None


def filter_json_by_bvids(json_path: str, bvids: set[str]) -> bool:
    try:
        if not os.path.exists(json_path):
            return False
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            return False
        if not bvids:
            # If no bvids provided, leave as is
            return True
        filtered = []
        for item in data:
            try:
                bv = (
                    (item.get('video') or {}).get('bvid')
                    or (item.get('comments') or {}).get('bvid')
                )
            except Exception:
                bv = None
            if bv in bvids:
                filtered.append(item)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)
        print(f"json filtered -> {json_path} kept={len(filtered)} of total={len(data)}")
        return True
    except Exception as e:
        print(f"[warn] filter json failed for {json_path}: {e}")
        return False
    


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
    ap.add_argument(
        "--keep_closed_if_title_match",
        action="store_true",
        help="keep rows when title matches keywords or closed-comment phrases are detected (applies only when --relaxed_filter)",
    )
    ap.add_argument(
        "--closed_phrases",
        default="关闭评论,评论区关闭,已关闭评论,禁止评论,UP主关闭了评论,作者关闭了评论",
        help="comma separated phrases indicating comments are closed",
    )
    ap.add_argument("--copy_json", action="store_true", help="copy monthly comments JSONs alongside merged results")
    ap.add_argument("--json_out_dir", default="data_merged_json", help="output dir for copied monthly JSONs")
    ap.add_argument("--copy_json_always", action="store_true", help="copy JSON even when merged CSV has zero rows")
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
        closed_phrases = [p.strip() for p in (args.closed_phrases or "").split(",") if p.strip()]
        for name, df in iterator:
            use_cols = [c for c in cols if c in df.columns]
            if not use_cols or not kws:
                if args.copy_json:
                    if args.copy_json_always or len(df) > 0:
                        ok, dst = choose_and_copy_json(name, args.dir_a, args.dir_b, args.json_out_dir)
                        if ok and dst:
                            bvids = set(df['bvid'].astype(str)) if 'bvid' in df.columns else set()
                            filter_json_by_bvids(dst, bvids)
                continue
            mask = False
            for c in use_cols:
                s = df[c].astype(str).str.lower()
                for kw in kws:
                    mask = mask | s.str.contains(kw.lower(), na=False)

            # 豁免：检测“评论区关闭”相关表述，或标题命中关键词时也保留
            extra_mask = False
            if args.keep_closed_if_title_match:
                # 关闭短语检测：在常见文本列里找提示信息
                closed_cols = [c for c in ["error_msg", "message", "text", "content", "desc"] if c in df.columns]
                for c in closed_cols:
                    s = df[c].astype(str)
                    for phrase in closed_phrases:
                        extra_mask = extra_mask | s.str.contains(phrase, na=False)
                # 标题命中：即使评论文本不匹配，只要标题包含关键词也保留
                if "title" in df.columns:
                    ts = df["title"].astype(str).str.lower()
                    for kw in kws:
                        extra_mask = extra_mask | ts.str.contains(kw.lower(), na=False)

            mask = mask | extra_mask
            dff = df[mask]
            out_path = os.path.join(args.filter_out_dir, name)
            dff.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"filtered -> {out_path} rows={len(dff)} (cols={','.join(use_cols)})")
            if args.copy_json:
                if args.copy_json_always or len(df) > 0:
                    ok, dst = choose_and_copy_json(name, args.dir_a, args.dir_b, args.json_out_dir)
                    if ok and dst:
                        # Prefer filtered bvids when relaxed_filter is on
                        bvids = set(dff['bvid'].astype(str)) if 'bvid' in dff.columns else (
                            set(df['bvid'].astype(str)) if 'bvid' in df.columns else set()
                        )
                        filter_json_by_bvids(dst, bvids)
    else:
        for name, df in iterator:
            if args.copy_json:
                if args.copy_json_always or len(df) > 0:
                    ok, dst = choose_and_copy_json(name, args.dir_a, args.dir_b, args.json_out_dir)
                    if ok and dst:
                        bvids = set(df['bvid'].astype(str)) if 'bvid' in df.columns else set()
                        filter_json_by_bvids(dst, bvids)


if __name__ == "__main__":
    main()
