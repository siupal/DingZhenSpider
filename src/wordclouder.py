from __future__ import annotations
import os
from typing import Iterable, List

import pandas as pd
import jieba
from wordcloud import WordCloud
import numpy as np
from PIL import Image
from wordcloud import ImageColorGenerator

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


DEFAULT_STOPWORDS = set(
    [
        "的","了","和","是","就","都","而","及","与","着","或","一个","没有","我们","你们","他们",
        "啊","呢","嘛","吧","哦","呀","哈","了不起","这个","那个","什么","还有","以及","以及",
        "哔哩哔哩","bilibili","视频","UP","up","UP主","作者","转载","原创","合集","官方","频道","投稿",
    ]
)


def build_corpus_from_csv(csv_path: str, columns: Iterable[str]) -> List[str]:
    df = pd.read_csv(csv_path)
    cols = [c for c in columns if c in df.columns]
    if not cols:
        # 兜底使用所有object列
        cols = [c for c in df.columns if df[c].dtype == object]
    texts: List[str] = []
    for c in cols:
        s = df[c].dropna().astype(str).tolist()
        texts.extend(s)
    return texts


def tokenize(texts: Iterable[str], extra_stopwords: Iterable[str] | None = None) -> str:
    stop = set(extra_stopwords or []) | DEFAULT_STOPWORDS
    tokens: List[str] = []
    for t in texts:
        for w in jieba.cut(t, HMM=True):
            w = w.strip()
            if not w:
                continue
            if len(w) <= 1:
                continue
            if w in stop:
                continue
            tokens.append(w)
    return " ".join(tokens)


def generate_wordcloud(
    text: str,
    output_path: str,
    max_words: int = 200,
    background_color: str = "white",
    font_path: str | None = None,
    width: int = 1600,
    height: int = 900,
    mask: np.ndarray | None = None,
    contour_width: int = 0,
    contour_color: str = "black",
    transparent: bool = False,
) -> str:
    # When rendering with transparent background (RGBA), WordCloud's contour drawing expects RGB arrays.
    # To avoid broadcasting errors, disable contour when transparent is True.
    effective_contour_width = 0 if transparent else contour_width
    wc = WordCloud(
        font_path=font_path,
        background_color=(None if transparent else background_color),
        mode=("RGBA" if transparent else "RGB"),
        max_words=max_words,
        width=width,
        height=height,
        mask=mask,
        contour_width=effective_contour_width,
        contour_color=contour_color,
    )
    img = wc.generate(text)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.to_file(output_path)
    return output_path


def load_mask(image_path: str, invert: bool = False, threshold: int = 128) -> np.ndarray:
    """Load an image and convert to a wordcloud mask (white=fillable, black=blocked).
    If your reference image is black shape on white background, set invert=True or use 255-mask.
    """
    arr = Image.open(image_path).convert("L")
    arr = np.array(arr)
    # Binarize
    mask = (arr > threshold).astype(np.uint8) * 255
    if invert:
        mask = 255 - mask
    return mask


def load_color_func(image_path: str) -> ImageColorGenerator:
    """Create a color function from a reference image for recoloring wordcloud."""
    img = np.array(Image.open(image_path).convert("RGB"))
    return ImageColorGenerator(img)


def _grabcut_mask(image_path: str, rect: tuple[int, int, int, int] | None = None, iter_count: int = 5) -> np.ndarray:
    """Build a foreground mask using GrabCut if OpenCV is available.
    rect = (x, y, w, h) rough rectangle containing the foreground. If None, use centered 70%.
    Returns binary mask (255=fillable, 0=blocked).
    """
    if cv2 is None:
        raise RuntimeError("OpenCV is not available. Install opencv-python-headless to use GrabCut.")
    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Failed to read image: {image_path}")
    h, w = img.shape[:2]
    if rect is None:
        rw, rh = int(w * 0.7), int(h * 0.7)
        rx, ry = (w - rw) // 2, (h - rh) // 2
        rect = (rx, ry, rw, rh)
    mask = np.zeros((h, w), np.uint8)
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, rect, bgdModel, fgdModel, iter_count, cv2.GC_INIT_WITH_RECT)
    # Probable/definite foreground -> 1, others 0
    mask_bin = np.where((mask == 1) | (mask == 3), 255, 0).astype("uint8")
    # Smooth edges
    kernel = np.ones((5, 5), np.uint8)
    mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel, iterations=2)
    return mask_bin


def generate_wordcloud_with_ref(
    text: str,
    output_path: str,
    font_path: str,
    mask_path: str | None = None,
    color_ref_path: str | None = None,
    invert_mask: bool = False,
    threshold: int = 128,
    segment: str = "threshold",  # 'threshold' | 'grabcut'
    rect: tuple[int, int, int, int] | None = None,
    max_words: int = 300,
    width: int = 1600,
    height: int = 1600,
    background_color: str = "white",
    contour_width: int = 3,
    contour_color: str = "#333333",
    transparent: bool = False,
    composite_on: str | None = None,
    opacity: float = 1.0,
    word_color: str | None = None,
    save_mask_path: str | None = None,
) -> str:
    mask = None
    if mask_path:
        if segment == "grabcut":
            try:
                mask = _grabcut_mask(mask_path, rect=rect)
            except Exception:
                # fallback to threshold if grabcut fails
                mask = load_mask(mask_path, invert=invert_mask, threshold=threshold)
        else:
            mask = load_mask(mask_path, invert=invert_mask, threshold=threshold)
    # Apply invert post-process so it also works for grabcut path
    if mask is not None and invert_mask and segment == "grabcut":
        mask = 255 - mask
    # optionally dump mask for debugging
    if mask is not None and save_mask_path:
        Image.fromarray(mask).save(save_mask_path)
    path = generate_wordcloud(
        text,
        output_path,
        max_words=max_words,
        background_color=background_color,
        font_path=font_path,
        width=width,
        height=height,
        mask=mask,
        contour_width=contour_width,
        contour_color=contour_color,
        transparent=transparent or bool(composite_on),
    )
    # If color reference is provided, recolor and overwrite
    if color_ref_path:
        # When transparent/compositing, disable contour to avoid RGBA vs RGB broadcasting issues
        effective_contour_width2 = 0 if (transparent or composite_on) else contour_width
        wc = WordCloud(
            font_path=font_path,
            background_color=(None if (transparent or composite_on) else background_color),
            mode=("RGBA" if (transparent or composite_on) else "RGB"),
            max_words=max_words,
            width=width,
            height=height,
            mask=mask,
            contour_width=effective_contour_width2,
            contour_color=contour_color,
        )
        wc.generate(text)
        colors = load_color_func(color_ref_path)
        wc = wc.recolor(color_func=colors)
        wc.to_file(output_path)
    elif word_color:
        # Monochrome recolor for silhouette-style words
        def solid_color_func(*args, **kwargs):
            return word_color
        # regenerate and recolor
        effective_contour_width2 = 0 if (transparent or composite_on) else contour_width
        wc = WordCloud(
            font_path=font_path,
            background_color=(None if (transparent or composite_on) else background_color),
            mode=("RGBA" if (transparent or composite_on) else "RGB"),
            max_words=max_words,
            width=width,
            height=height,
            mask=mask,
            contour_width=effective_contour_width2,
            contour_color=contour_color,
        )
        wc.generate(text)
        wc = wc.recolor(color_func=solid_color_func)
        wc.to_file(output_path)

    # Composite wordcloud in front of the reference/base image if requested
    if composite_on:
        base = Image.open(composite_on).convert("RGBA")
        wc_img = Image.open(output_path).convert("RGBA")
        if opacity < 1.0:
            alpha = wc_img.split()[-1].point(lambda a: int(a * max(0.0, min(1.0, opacity))))
            wc_img.putalpha(alpha)
        # paste with alpha so wordcloud stays in foreground
        base.alpha_composite(wc_img.resize(base.size))
        base.save(output_path)
    return path
