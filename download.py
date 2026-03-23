import os
import re
import shutil
import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests


def _http_base_dir(url: str) -> str:
    u = urlparse(url)
    path = u.path or "/"
    if path.endswith("/"):
        dir_path = path
    else:
        dir_path = path.rsplit("/", 1)[0] + "/"
    return urlunparse((u.scheme, u.netloc, dir_path, "", "", ""))


def load_playlist_text_and_base(path_or_url: str) -> tuple[str, str]:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        r = requests.get(path_or_url, timeout=120)
        r.raise_for_status()
        return r.text, _http_base_dir(path_or_url)

    p = Path(path_or_url).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Not a file: {p}")
    text = p.read_text(encoding="utf-8")
    base = p.parent.as_uri()
    if not base.endswith("/"):
        base += "/"
    return text, base


def _split_hls_attr_value(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    n = len(rest)
    while i < n:
        while i < n and rest[i] in " \t":
            i += 1
        if i >= n:
            break
        eq = rest.find("=", i)
        if eq == -1:
            break
        key = rest[i:eq].strip()
        i = eq + 1
        if i < n and rest[i] == '"':
            end = rest.find('"', i + 1)
            if end == -1:
                out[key] = rest[i + 1 :]
                break
            out[key] = rest[i + 1 : end]
            i = end + 1
        else:
            j = i
            while j < n and rest[j] != ",":
                j += 1
            out[key] = rest[i:j].strip()
            i = j + 1
    return out


def _parse_stream_inf(line: str) -> dict[str, str]:
    if not line.startswith("#EXT-X-STREAM-INF:"):
        return {}
    return _split_hls_attr_value(line[len("#EXT-X-STREAM-INF:") :])


def parse_master_variants(playlist: str) -> list[dict]:
    lines = playlist.splitlines()
    variants: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXT-X-STREAM-INF") and "I-FRAME" not in line:
            attrs = _parse_stream_inf(line)
            uri = None
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if s.startswith("#"):
                    break
                uri = s
                break
            if uri:
                bw = attrs.get("BANDWIDTH")
                res = attrs.get("RESOLUTION")
                height = None
                width = None
                if res and "x" in res:
                    parts = res.lower().split("x", 1)
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        width, height = int(parts[0]), int(parts[1])
                variants.append(
                    {
                        "uri": uri,
                        "bandwidth": int(bw) if bw and bw.isdigit() else None,
                        "resolution": res,
                        "width": width,
                        "height": height,
                    }
                )
        i += 1
    return variants


def is_master_playlist(text: str) -> bool:
    return bool(parse_master_variants(text))


def _variant_label(v: dict, index: int) -> str:
    parts = [f"[{index}]"]
    if v.get("resolution"):
        parts.append(v["resolution"])
    if v.get("bandwidth") is not None:
        parts.append(f"{v['bandwidth']} bps")
    return " ".join(parts)


def select_variant(variants: list[dict], spec: str) -> tuple[dict, str]:
    if not variants:
        raise ValueError("Master playlist has no EXT-X-STREAM-INF variants")

    s = spec.strip().lower()
    if s == "best":
        with_bw = [v for v in variants if v.get("bandwidth") is not None]
        if with_bw:
            chosen = max(with_bw, key=lambda x: x["bandwidth"])
        else:
            chosen = variants[0]
        idx = variants.index(chosen)
        return chosen, _variant_label(chosen, idx)

    if s == "worst":
        with_bw = [v for v in variants if v.get("bandwidth") is not None]
        if with_bw:
            chosen = min(with_bw, key=lambda x: x["bandwidth"])
        else:
            chosen = variants[-1]
        idx = variants.index(chosen)
        return chosen, _variant_label(chosen, idx)

    m = re.fullmatch(r"i(\d+)", s)
    if m:
        idx = int(m.group(1))
        if idx < 0 or idx >= len(variants):
            raise ValueError(
                f"Variant index {idx} out of range (0..{len(variants) - 1})"
            )
        v = variants[idx]
        return v, _variant_label(v, idx)

    m = re.fullmatch(r"(\d+)\s*x\s*(\d+)", s.replace(" ", ""))
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        for idx, v in enumerate(variants):
            if v.get("width") == w and v.get("height") == h:
                return v, _variant_label(v, idx)
        raise ValueError(f"No variant with resolution {w}x{h}")

    if re.fullmatch(r"\d{3,4}", s):
        h = int(s)
        matches = [v for v in variants if v.get("height") == h]
        if matches:
            chosen = max(matches, key=lambda x: x.get("bandwidth") or 0)
            idx = variants.index(chosen)
            return chosen, _variant_label(chosen, idx)

    if s.isdigit():
        idx = int(s)
        if idx < 0 or idx >= len(variants):
            raise ValueError(
                f"Variant index {idx} out of range (0..{len(variants) - 1})"
            )
        v = variants[idx]
        return v, _variant_label(v, idx)

    raise ValueError(
        "Invalid --variant: best, worst, iN (index), 360..2160 (height), or WxH"
    )


def resolve_playlist_uri(base: str, uri: str) -> str:
    return urljoin(base, uri)


def extract_segment_urls(playlist: str) -> list[str]:
    urls: list[str] = []
    for line in playlist.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls


def download_segments(segment_urls: list[str], base: str, segments_dir: str) -> None:
    os.makedirs(segments_dir, exist_ok=True)
    for i, seg in enumerate(segment_urls, start=1):
        seg_url = resolve_playlist_uri(base, seg)
        print(f"Downloading {i}/{len(segment_urls)}: {seg_url}")
        r = requests.get(seg_url, stream=True, timeout=120)
        r.raise_for_status()
        segment_path = os.path.join(segments_dir, f"seg_{i:04d}.bin")
        with open(segment_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def merge_segments(segment_count: int, segments_dir: str, merged_path: str) -> None:
    with open(merged_path, "wb") as merged:
        for i in range(1, segment_count + 1):
            segment_path = os.path.join(segments_dir, f"seg_{i:04d}.bin")
            with open(segment_path, "rb") as seg:
                merged.write(seg.read())


def run_ffmpeg(merged_path: str, output_file: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", merged_path, "-c", "copy", output_file],
        check=True,
    )


def download_m3u8(path_or_url: str, output_file: str, variant_spec: str) -> None:
    segments_dir = "segments"
    merged_ts = "merged.ts"

    os.makedirs(segments_dir, exist_ok=True)

    text, base = load_playlist_text_and_base(path_or_url)

    if is_master_playlist(text):
        variants = parse_master_variants(text)
        chosen, label = select_variant(variants, variant_spec)
        print(f"Using variant: {label}")
        media_url = resolve_playlist_uri(base, chosen["uri"])
        text, base = load_playlist_text_and_base(media_url)

    segment_urls = extract_segment_urls(text)
    if not segment_urls:
        raise RuntimeError(
            "No segment lines found in media playlist (nothing to download)"
        )

    try:
        download_segments(segment_urls, base, segments_dir)
        merge_segments(len(segment_urls), segments_dir, merged_ts)
        run_ffmpeg(merged_ts, output_file)
    finally:
        print("Cleaning up temporary files...")
        if os.path.exists(merged_ts):
            os.remove(merged_ts)
        if os.path.exists(segments_dir):
            shutil.rmtree(segments_dir)

    print(f"\nDownload complete: {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download HLS (M3U8) media playlist and mux to MP4"
    )
    parser.add_argument(
        "m3u8",
        help="Local path to .m3u8 or HTTP(S) URL (master or media playlist)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output.mp4",
        help="Output file (default: output.mp4)",
    )
    parser.add_argument(
        "-V",
        "--variant",
        default="best",
        metavar="SPEC",
        help="Master only: best, worst, i0 (index), 1080 (height), 1920x1080",
    )

    args = parser.parse_args()

    print(f"Source: {args.m3u8}")
    print(f"Output: {args.output}")
    print()

    try:
        download_m3u8(args.m3u8, args.output, args.variant)
    except (requests.RequestException, subprocess.CalledProcessError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
