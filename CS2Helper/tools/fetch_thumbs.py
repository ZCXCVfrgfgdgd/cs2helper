#!/usr/bin/env python3
"""
CS2 Helper - thumbnail downloader.

Runs once, from the project root:

    python tools/fetch_thumbs.py

It asks Steam's public API for the preview image of every workshop item used
by index.html, saves each one as img/<publishedfileid>.jpg, and writes a small
manifest (img/thumbs.json) so you can see what came from where.

index.html then loads those files directly from disk, so the browser never
talks to Steam and there is no CORS involved at all - it works over file://
just as well as over a local server.

Standard library only. No pip install needed.
"""

import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

# --- every workshop item in index.html, grouped the same way ----------------
IDS = {
    "aim hub": [
        "3604696412",  # TRAINING.01 - Warmup Map
        "3070715607",  # Yprac Hub by Yesber
        "3086023598",  # 5e_aimhub
        "3416003536",  # Refrag.gg
        "3303464810",  # SC Aim Course v3.0
        "3070244462",  # Aim Botz
        "3083320026",  # Fast Warmup - Bot Training
        "3070389038",  # CSStats Training Map (CSGOHUB)
        "3124182019",  # aim_treeni
        "3105821815",  # Aim_Rush
    ],
    "prefire (valve pool)": [
        "3267302800",  # Mirage
        "3282067356",  # Ancient
        "3318295422",  # Nuke
        "3289507717",  # Inferno
        "3307639951",  # Anubis
        "3295650711",  # Dust 2
        "3770489042",  # Cache
    ],
    "prefire (other)": [
        "3328383138",  # Overpass
        "3562576256",  # Train
        "3274138705",  # Vertigo
    ],
    "utility": [
        "3312981414",  # Mirage
        "3332771164",  # Inferno
        "3340925621",  # Nuke
        "3351615311",  # Ancient
        "3360435602",  # Dust 2
        "3368313759",  # Anubis (old)
        "3566472167",  # Overpass
    ],
    "other": [
        "1365781615",  # yprac recoil
        "3100869952",  # recoil master
        "3702432002",  # DHL B sites
        "3482314780",  # DHL A sites
    ],
}

API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
UA = "Mozilla/5.0 (CS2Helper thumbnail fetcher)"
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
IMG_DIR = os.path.normpath(IMG_DIR)
# width of the stored image; Steam resizes server-side
WIDTH = 1024

CTX = ssl.create_default_context()


def api_details(ids):
    """Ask Steam for details of up to 100 items in one request."""
    body = [("itemcount", str(len(ids)))]
    for i, pid in enumerate(ids):
        body.append((f"publishedfileids[{i}]", pid))
    data = urllib.parse.urlencode(body).encode()
    req = urllib.request.Request(API, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read().decode()).get("response", {}).get(
            "publishedfiledetails", []
        )


def sized(url, width):
    """Ask the Steam CDN for a reasonably sized copy instead of the original."""
    if not url:
        return url
    base = url.split("?")[0]
    return (
        f"{base}?imw={width}&ima=fit&impolicy=Letterbox"
        f"&imcolor=%23000000&letterbox=false"
    )


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        blob = r.read()
    if len(blob) < 1024:
        raise ValueError(f"suspiciously small file ({len(blob)} bytes)")
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)


def main():
    all_ids = [pid for group in IDS.values() for pid in group]
    os.makedirs(IMG_DIR, exist_ok=True)
    print(f"{len(all_ids)} workshop items -> {IMG_DIR}\n")

    try:
        details = api_details(all_ids)
    except Exception as e:
        print(f"Could not reach the Steam API: {e}")
        print("Check your connection (or a VPN, if Steam is blocked) and retry.")
        return 1

    by_id = {d.get("publishedfileid"): d for d in details}
    manifest, ok, skipped, failed = {}, 0, 0, []

    for pid in all_ids:
        dest = os.path.join(IMG_DIR, f"{pid}.jpg")
        title = (by_id.get(pid) or {}).get("title", "?")

        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            manifest[pid] = {"file": f"img/{pid}.jpg", "title": title}
            skipped += 1
            print(f"  = {pid}  already here   {title}")
            continue

        preview = (by_id.get(pid) or {}).get("preview_url")
        if not preview:
            failed.append((pid, "no preview in the API response (item hidden or removed)"))
            print(f"  ! {pid}  no preview")
            continue

        try:
            size = download(sized(preview, WIDTH), dest)
        except Exception as e:
            failed.append((pid, str(e)))
            print(f"  ! {pid}  {e}")
            continue

        manifest[pid] = {"file": f"img/{pid}.jpg", "title": title, "source": preview}
        ok += 1
        print(f"  + {pid}  {size // 1024:>4} KB   {title}")

    with open(os.path.join(IMG_DIR, "thumbs.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\ndownloaded {ok}, already present {skipped}, missing {len(failed)}")
    if failed:
        print("\nMissing ones - grab a screenshot from the workshop page and save it")
        print("as img/<id>.jpg by hand; index.html picks it up with no other change:")
        for pid, why in failed:
            print(f"  {pid}  ({why})")
            print(f"    https://steamcommunity.com/sharedfiles/filedetails/?id={pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
