import argparse
import sys
import json
import asyncio

from playwright.async_api import async_playwright

NOTE_INFOS_SCRIPT = '''
() => {
    const infos = [];
    for (const note of song.notes) {
        infos.push({
            instrument: note.instrument,
            type: note.type,
            time: note.time * (60/bpm/4),
            length: note.length * (60/bpm/4),
            volume: note.volume,
        });
    }
    return infos;
}
'''

INSTRUMENT_SETTINGS_SCRIPT = '''
() => {
    const instrument_settings = {};
    for (const instrument in song.settings.instrument) {
        const settings = song.settings.instrument[instrument]
        instrument_settings[instrument] = {
            volume: settings[instrument],
        };
    }
    return instrument_settings;
}
'''

async def get_note_infos(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        note_infos = await page.evaluate(NOTE_INFOS_SCRIPT)
        instrument_settings = await page.evaluate(INSTRUMENT_SETTINGS_SCRIPT)
        def _scale_volume():
            for note_info in note_infos:
                instrument = note_info["instrument"]
                if instrument not in instrument_settings:
                    continue
                settings = instrument_settings[instrument]
                volume = settings.get("volume", 1)
                note_info["volume"] *= volume
        await asyncio.to_thread(_scale_volume)
        await browser.close()
    return note_infos

parser = argparse.ArgumentParser(
    description="Gets all notes from an Online Sequencer song.",
)
parser.add_argument(
    "url",
    help="link to the song to extract note infos from",
)

if __name__ == "__main__":
    args = parser.parse_args()
    note_infos = asyncio.run(get_note_infos(args.url))
    json.dump(sys.stdout, note_infos, separators=[",",":"])
