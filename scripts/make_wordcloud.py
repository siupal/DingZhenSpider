from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when running this script directly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.wordclouder import (  # type: ignore
    build_corpus_from_csv,
    tokenize,
    generate_wordcloud_with_ref,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate wordcloud from CSV using a reference image (shape+colors)")
    p.add_argument("--csv", required=True, help="CSV path, e.g., data/popular.csv")
    p.add_argument("--columns", nargs="+", default=["title", "tname"], help="Columns to use, e.g., title tname desc")
    p.add_argument("--font", required=True, help="Font path for Chinese, e.g., C:/Windows/Fonts/msyh.ttc")
    p.add_argument("--ref", required=True, help="Reference image path for mask and colors, e.g., assets/color.png")
    p.add_argument("--invert_mask", action="store_true", help="Invert binarized mask if your shape is dark on white background")
    p.add_argument("--threshold", type=int, default=128, help="Binarization threshold for mask (default 128)")
    p.add_argument("--segment", choices=["threshold", "grabcut"], default="threshold", help="Mask method: threshold (default) or grabcut (requires OpenCV)")
    p.add_argument("--rect", nargs=4, type=int, metavar=("x","y","w","h"), help="GrabCut rect: x y w h. If omitted, auto-centered 70% is used")
    p.add_argument("--max_words", type=int, default=300, help="Max words in wordcloud")
    p.add_argument("--width", type=int, default=1600, help="Output width")
    p.add_argument("--height", type=int, default=1600, help="Output height")
    p.add_argument("--background", default="white", help="Background color, set None for transparent (not implemented here)")
    p.add_argument("--contour_width", type=int, default=3, help="Contour width")
    p.add_argument("--contour_color", default="#333333", help="Contour color")
    p.add_argument("--out", default=None, help="Output png path, default data/wordcloud_<csvname>.png")
    # Foreground compositing
    p.add_argument("--composite_on", help="Place wordcloud in front of this image (usually same as --ref)")
    p.add_argument("--opacity", type=float, default=1.0, help="Wordcloud opacity when compositing (0~1)")
    p.add_argument("--transparent", action="store_true", help="Render wordcloud with transparent background (useful for compositing)")
    return p.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.csv):
        raise SystemExit(f"CSV not found: {args.csv}")
    if not os.path.exists(args.ref):
        raise SystemExit(f"Reference image not found: {args.ref}")
    if not os.path.exists(args.font):
        raise SystemExit(f"Font not found: {args.font}")

    texts = build_corpus_from_csv(args.csv, args.columns)
    text = tokenize(texts)

    safe_name = os.path.splitext(os.path.basename(args.csv))[0]
    out_path = args.out or os.path.join("data", f"wordcloud_{safe_name}.png")

    generate_wordcloud_with_ref(
        text=text,
        output_path=out_path,
        font_path=args.font,
        mask_path=args.ref,
        color_ref_path=args.ref,
        invert_mask=bool(args.invert_mask),
        threshold=int(args.threshold),
        segment=args.segment,
        rect=tuple(args.rect) if args.rect else None,
        max_words=int(args.max_words),
        width=int(args.width),
        height=int(args.height),
        background_color=args.background,
        contour_width=int(args.contour_width),
        contour_color=args.contour_color,
        transparent=bool(args.transparent or args.composite_on),
        composite_on=args.composite_on,
        opacity=float(args.opacity),
    )
    print("Saved:", out_path)


if __name__ == "__main__":
    main()
