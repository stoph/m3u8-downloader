import os
import sys
import shutil
import argparse
import requests
from urllib.parse import urljoin

def download_m3u8(m3u8_url, output_file="output.mp4"):
    # Create a temp directory
    os.makedirs("segments", exist_ok=True)

    # Download m3u8 playlist
    playlist = requests.get(m3u8_url).text
    base_url = m3u8_url.rsplit("/", 1)[0]

    ts_files = [line.strip() for line in playlist.splitlines() if line.endswith(".ts")]

    # Download each TS file
    for i, ts_file in enumerate(ts_files, start=1):
        ts_url = urljoin(base_url + "/", ts_file)
        print(f"Downloading {i}/{len(ts_files)}: {ts_url}")
        r = requests.get(ts_url, stream=True)
        segment_path = f"segments/seg_{i:04d}.ts"
        with open(segment_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Merge all segments into one .ts file
    with open("merged.ts", "wb") as merged:
        for i in range(1, len(ts_files) + 1):
            with open(f"segments/seg_{i:04d}.ts", "rb") as seg:
                merged.write(seg.read())

    # Convert to .mp4 (requires ffmpeg installed)
    os.system(f'ffmpeg -y -i merged.ts -c copy "{output_file}"')

    # Clean up temporary files
    print("Cleaning up temporary files...")
    if os.path.exists("merged.ts"):
        os.remove("merged.ts")
    if os.path.exists("segments"):
        shutil.rmtree("segments")

    print(f"\n✅ Download complete: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download M3U8 playlist and convert to MP4")
    parser.add_argument("m3u8_url", help="URL to the M3U8 playlist file")
    parser.add_argument("-o", "--output", default="output.mp4", help="Output video file name (default: output.mp4)")
    
    args = parser.parse_args()
    
    print(f"Downloading from: {args.m3u8_url}")
    print(f"Output file: {args.output}")
    print()
    
    download_m3u8(args.m3u8_url, args.output)