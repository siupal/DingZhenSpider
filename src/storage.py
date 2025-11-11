from __future__ import annotations
import os
import csv
import sqlite3
from typing import List, Dict, Any

import pandas as pd
import json


COLUMNS = [
    "bvid",
    "title",
    "tname",
    "pubdate",
    "duration",
    "owner",
    "view",
    "danmaku",
    "reply",
    "favorite",
    "coin",
    "share",
    "like",
]


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_csv(items: List[Dict[str, Any]], csv_path: str) -> None:
    df_new = pd.DataFrame(items, columns=COLUMNS)
    if os.path.exists(csv_path):
        df_old = pd.read_csv(csv_path)
        df = pd.concat([df_old, df_new], ignore_index=True)
        df = df.sort_values(by=["view", "like"], ascending=[False, False])
        df = df.drop_duplicates(subset=["bvid"], keep="first")
    else:
        df = df_new
    df.to_csv(csv_path, index=False)


def init_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                bvid TEXT PRIMARY KEY,
                title TEXT,
                tname TEXT,
                pubdate INTEGER,
                duration INTEGER,
                owner TEXT,
                view INTEGER,
                danmaku INTEGER,
                reply INTEGER,
                favorite INTEGER,
                coin INTEGER,
                share INTEGER,
                like INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_sqlite(items: List[Dict[str, Any]], db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        sql = (
            "INSERT OR REPLACE INTO videos (" + ",".join(COLUMNS) + ") "
            "VALUES (" + ",".join(["?" for _ in COLUMNS]) + ")"
        )
        rows = [tuple(item.get(col) for col in COLUMNS) for item in items]
        conn.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def persist_all(items: List[Dict[str, Any]], output_dir: str, basename: str = "videos") -> Dict[str, str]:
    ensure_dir(output_dir)
    csv_path = os.path.join(output_dir, f"{basename}.csv")
    db_path = os.path.join(output_dir, f"{basename}.sqlite")
    init_sqlite(db_path)
    # Always create/update CSV and SQLite, even when items is empty
    # so that monthly tasks always produce expected artifacts.
    save_csv(items, csv_path)
    save_sqlite(items, db_path)
    return {"csv": csv_path, "sqlite": db_path}


def save_json(data: Any, path: str) -> str:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
