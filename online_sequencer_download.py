import argparse
import json
import asyncio
import os
import subprocess
import re

import httpx

def _extract_data(text):
    """Extracts the base64 encoded string from the site's JavaScript"""
    # This is more fragile than a nuclear bomb
    return base64.b64decode(re.search(r"var data = '([^']*)';", text)[1])

async def get_instrument_settings():
    # Get JS filename
    async with httpx.AsyncClient() as client:
        response = await client.get("https://onlinesequencer.net/")
    # More fragile than your mom
    match = re.search(
        r'<script type="text/javascript" src="(/resources/[^"]*)"></script>',
        response.text,
    )
    if match is None:
        raise RuntimeError("resources script not found")
    filename = match[1].lstrip("/")
    # Get settings JSON
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://onlinesequencer.net/{filename}")
    match = re.search(r"var settings=({(?:(?!};).)*});", response.text)
    if match is None:
        raise RuntimeError("settings JSON not found")
    return json.loads(match[1])

def download_instrument_audio(directory, instrument):
    url = f"https://onlinesequencer.net/app/instruments/{instrument}.ogg?v=12"
    destination = f"{directory}/{instrument}.ogg"
    subprocess.run([
        "ffmpeg",
        "-nostdin",
        "-y",
        "-loglevel", "error",
        "-i", url,
        "-acodec", "copy",
        destination,
    ], check=True)

def main(directory):
    print("Ensuring the directory exists...")
    os.makedirs(directory, exist_ok=True)

    print("Getting instrument settings...")
    instrument_settings = asyncio.run(get_instrument_settings())
    print("Writing instrument settings...")
    with open(f"{directory}/settings.json", mode="w") as file:
        json.dump(instrument_settings, file)

    original_bpms = instrument_settings["originalBpm"]
    print(
        "Downloading instrument audio files..."
        f" ({len(original_bpms)} in total)"
    )
    for instrument, original_bpm in enumerate(original_bpms):
        if original_bpm == 0:
            print(f"Skipping instrument {instrument}...")
            continue
        print(f"Downloading audio file for instrument {instrument}...")
        download_instrument_audio(directory, instrument)

parser = argparse.ArgumentParser(
    description="Downloads Online Sequencer settings and audio files.",
)
parser.add_argument(
    "directory",
    default="oscollection",
    help="name of the directory to use",
)

if __name__ == "__main__":
    args = parser.parse_args()
    main(args.directory)
