"""Download a real, freely licensed photo for every vehicle in the fleet.

Photos come from Wikipedia / Wikimedia Commons (Creative Commons or public domain),
so they are safe to use on a public site as long as the author and licence are credited.
The app shows that credit under each photo automatically from credits.json.

Usage (from the backend folder):
    python scripts/fetch_vehicle_photos.py            # fetch photos that are missing
    python scripts/fetch_vehicle_photos.py --force    # re-fetch everything
    python scripts/fetch_vehicle_photos.py LX-007     # just one vehicle

Your own photos: drop a JPG named after the vehicle ID (e.g. LX-007.jpg) into
frontend/img/fleet/ and add an entry to credits.json with "author": "Oyibo Rentals".
"""

from __future__ import annotations

import html
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.seed import FLEET, PHOTO_ARTICLES  # noqa: E402

from app.config import PHOTO_DIR as OUT  # noqa: E402
CREDITS = OUT / "credits.json"
UA = "OyiboRentals/2.1 (student project; https://github.com/) python-urllib"
WIDTH = 960

# Where the article's lead image isn't a photo of the vehicle (a logo, a factory), pick the first
# photo on the article whose file name contains one of these words.
PREFER_WORDS = {
    "BK-005": ["spiro", "motorcycle", "bike"],
}


def get_json(url: str, tries: int = 8) -> dict:
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(min(60, 4 * 2 ** attempt))
                continue
            if e.code == 404:
                return {}
            raise
    return {}


def get_bytes(url: str, tries: int = 8) -> bytes:
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(min(60, 4 * 2 ** attempt))
                continue
            raise
    raise RuntimeError("download failed")


def usable(file_title: str) -> bool:
    t = file_title.lower()
    return t.endswith((".jpg", ".jpeg", ".webp")) and not any(w in t for w in ("logo", "emblem", "badge", "map", "diagram"))


def lead_image(article: str) -> str | None:
    data = get_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(article.replace(" ", "_")))
    src = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
    if not src:
        return None
    name = urllib.parse.unquote(src.split("?")[0].rstrip("/").split("/")[-1])
    name = re.sub(r"^\d+px-", "", name)
    return "File:" + name


def article_photos(article: str) -> list[str]:
    params = {"action": "query", "format": "json", "titles": article, "prop": "images", "imlimit": 50, "redirects": 1}
    data = get_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params))
    titles = []
    for page in data.get("query", {}).get("pages", {}).values():
        titles += [i["title"] for i in page.get("images", []) if usable(i["title"])]
    return titles


def search_commons(query: str) -> str | None:
    params = {"action": "query", "format": "json", "list": "search", "srnamespace": 6, "srlimit": 10,
              "srsearch": f"{query} filetype:bitmap"}
    data = get_json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
    for hit in data.get("query", {}).get("search", []):
        if usable(hit["title"]):
            return hit["title"]
    return None


def file_info(file_title: str) -> dict | None:
    params = {"action": "query", "format": "json", "titles": file_title, "prop": "imageinfo",
              "iiprop": "url|extmetadata", "iiurlwidth": WIDTH}
    data = get_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params))
    for page in data.get("query", {}).get("pages", {}).values():
        if page.get("imageinfo"):
            return page["imageinfo"][0]
    return None


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value or ""))).strip()


def save_jpeg(raw: bytes, path: Path) -> None:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > WIDTH:
            img = img.resize((WIDTH, round(img.height * WIDTH / img.width)))
        img.save(path, "JPEG", quality=82, optimize=True, progressive=True)
    except ImportError:  # Pillow is optional; keep the original bytes
        path.write_bytes(raw)


def main(argv: list[str]) -> None:
    force = "--force" in argv
    only = {a for a in argv if not a.startswith("--")}
    OUT.mkdir(parents=True, exist_ok=True)
    credits = json.loads(CREDITS.read_text()) if CREDITS.exists() else {}
    names = {row[0]: f"{row[2]} {row[3]}" for row in FLEET}

    for vid, article in PHOTO_ARTICLES.items():
        if only and vid not in only:
            continue
        target = OUT / f"{vid}.jpg"
        if target.exists() and vid in credits and not force:
            continue
        try:
            fetch_one(vid, article, target, names, credits)
        except Exception as e:  # keep going; re-run later to fill gaps
            print(f"  ! {vid:7} {names.get(vid)} — {e}; re-run the script to retry")
        time.sleep(2.5)  # be polite to Wikimedia

    print(f"\n{len(credits)} photos in {OUT}")


def fetch_one(vid, article, target, names, credits):
    title = lead_image(article)
    words = PREFER_WORDS.get(vid)
    if not title or not usable(title) or (words and not any(w in title.lower() for w in words)):
        photos = article_photos(article)
        picks = [t for t in photos if words and any(w in t.lower() for w in words)] or photos
        title = picks[0] if picks else None
    info = file_info(title) if title else None
    if not info:
        print(f"  ✗ {vid:7} {names.get(vid)} — no free photo found; the app will show an illustration")
        return
    meta = info.get("extmetadata", {})
    save_jpeg(get_bytes(info.get("thumburl") or info["url"]), target)
    credits[vid] = {
        "file": f"img/fleet/{vid}.jpg",
        "title": title.removeprefix("File:"),
        "author": plain(meta.get("Artist", {}).get("value", "")) or "Unknown author",
        "license": plain(meta.get("LicenseShortName", {}).get("value", "")) or "See source",
        "license_url": plain(meta.get("LicenseUrl", {}).get("value", "")),
        "source": info.get("descriptionurl", ""),
    }
    CREDITS.write_text(json.dumps(credits, indent=2, ensure_ascii=False))
    print(f"  ✓ {vid:7} {names.get(vid):32} {credits[vid]['license']:14} {credits[vid]['author'][:40]}")


if __name__ == "__main__":
    main(sys.argv[1:])
