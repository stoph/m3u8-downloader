# M3U8 downloader

Downloads an HLS media playlist and muxes it to MP4 with ffmpeg.

## Requirements

- Python 3
- `requests` (`pip install requests`)
- `ffmpeg` on `PATH`

## Usage

```bash
python download.py <path-or-url> [-o out.mp4] [-V variant]
```

Use a **media** playlist (lists segments) or a **master** playlist (lists variants). For a master playlist, pick a variant with `-V` (default `best`).

**`-V` (master only)**

| Form | Meaning |
|------|--------|
| `best` / `worst` | Highest or lowest bandwidth |
| `i0`, `i1`, … | Variant by order in the file |
| `1080`, `720`, `360` | Match height (pixels) |
| `1920x1080` | Exact resolution |

## Examples

```bash
python download.py ./playlist.m3u8 -o video.mp4
python download.py https://example.com/master.m3u8 -V 1080 -o video.mp4
python download.py https://example.com/master.m3u8 -V i2 -o video.mp4
```
