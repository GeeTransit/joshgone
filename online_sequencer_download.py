import argparse
import json
import asyncio
import os
import subprocess

from playwright.async_api import async_playwright

async def get_instrument_settings():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://onlinesequencer.net/")
        instrument_settings = await page.evaluate("settings")
        await browser.close()
    return instrument_settings

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
