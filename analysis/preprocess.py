import os
import json
import re
import pandas as pd
from typing import List, Dict, Any

_url_re = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_ws_re = re.compile(r"\s+")


def _clean_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = _url_re.sub(" ", s)
    s = s.replace("\u200b", " ")
    s = _ws_re.sub(" ", s).strip()
    return s


def _extract_rows(payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in payload or []:
        v = it.get("video") or {}
        cm = it.get("comments") or {}
        bvid = v.get("bvid") or cm.get("bvid")
        replies = (cm.get("replies") or [])
        for c in replies:
            out.append({
                "bvid": bvid,
                "rpid": c.get("rpid"),
                "parent": c.get("parent"),
                "floor": c.get("floor"),
                "like": c.get("like"),
                "ctime": c.get("ctime"),
                "uname": c.get("uname"),
                "mid": c.get("mid"),
                "message": _clean_text(c.get("message")),
            })
    return out


def load_and_clean(input_dir: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for fn in os.listdir(input_dir):
        if not fn.lower().endswith(".json"):
            continue
        if not fn.startswith("comments_"):
            continue
        path = os.path.join(input_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            rows.extend(_extract_rows(payload))
        except Exception:
            continue
    if not rows:
        out_csv = os.path.join(output_dir, "comments_cleaned.csv")
        pd.DataFrame([], columns=["bvid","rpid","parent","floor","like","ctime","uname","mid","message"]).to_csv(out_csv, index=False)
        return out_csv
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["rpid"], keep="first")
    out_csv = os.path.join(output_dir, "comments_cleaned.csv")
    df.to_csv(out_csv, index=False)
    return out_csv


def main():
    input_dir = os.environ.get("DZ_INPUT_DIR", "data")
    output_dir = os.environ.get("DZ_ANALYSIS_DIR", os.path.join("analysis", "cleaned"))
    path = load_and_clean(input_dir, output_dir)
    print(path)


if __name__ == "__main__":
    main()
