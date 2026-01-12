# M3U8 Downloader

A simple Python script to download M3U8 playlists and convert them to MP4 videos.

## Requirements

- Python 3.6+
- ffmpeg (must be installed and available in PATH)

## Installation

1. Clone this repository
2. Install Python dependencies:
   ```bash
   pip install requests
   ```

## Usage

```bash
python download.py <m3u8_url> [-o output_file.mp4]
```

### Examples

```bash
# Basic usage
python download.py https://example.com/playlist.m3u8

# With custom output filename
python download.py https://example.com/playlist.m3u8 -o my_video.mp4
```

## How it works

1. Downloads the M3U8 playlist file
2. Extracts all TS segment URLs
3. Downloads each TS segment
4. Merges all segments into a single TS file
5. Converts to MP4 using ffmpeg
6. Cleans up temporary files

## Notes

- Temporary files (`segments/` directory and `merged.ts`) are automatically cleaned up
- The script requires ffmpeg to be installed on your system
