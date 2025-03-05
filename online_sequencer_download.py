import argparse
import json
import ast
import asyncio
import os
import subprocess
import re

import httpx

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
    settings = json.loads(match[1].replace("!1", "false"))  # why
    match_samples = re.search(r"const kSampleMap=([^;]*);", response.text)
    if match_samples:
        # The keys are ints but luckily it can be interpreted as a Python dict
        kSampleMap = ast.literal_eval(match_samples[1])
        settings["kSampleMap"] = {str(k): v for k, v in kSampleMap.items()}
    return settings

def download_instrument_audio(directory, instrument, *, sampler=False):
    url = f"https://onlinesequencer.net/app/instruments/{instrument}.ogg?v=12"
    if sampler:
        url = url.replace("instruments/", "instruments/sampler/")
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
            if str(instrument) in instrument_settings.get("kSampleMap", {}):
                print(f"Downloading audio file for instrument {instrument}...")
                download_instrument_audio(directory, instrument, sampler=True)
                continue
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
