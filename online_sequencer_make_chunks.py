import argparse
import sys
import json

import soundit as s

def make_chunks(infos, **kwargs):
    """Generate chunks from note infos"""
    return s.chunked(make_sound(infos, **kwargs))

def make_sound(note_infos, *, settings, template, cache=None):
    """Generate a sound from note infos"""

    # Cached to be a tad bit faster (removes float conversion step)
    @s.lru_iter_cache(maxsize=16)
    def instrument_sound_at(instrument, note_index):
        chunks = instrument_chunks_at(instrument, note_index)
        sound = s.unchunked(chunks)
        if not getattr(s, "has_numpy", False):
            return ((x+y)/2 for x, y in sound)
        return s.single(sound)

    # Cached so that we don't start up 2000 FFmpeg processes
    @s.lru_iter_cache(cache=cache)
    def instrument_chunks_at(instrument, note_index):
        filename = template.replace("<>", str(instrument))
        if settings["originalBpm"][instrument] != 0:
            length = 60 / (settings["originalBpm"][instrument] * 2)
            start = (note_index - settings["min"][instrument] - 24) * length
        else:
            length = 41 if instrument == 44 else 12 if instrument == 54 else 16
            start = note_index * length
        length -= 0.005  # Some files have noise at the end
        if not getattr(s, "has_av", False):
            args = s.make_ffmpeg_section_args(filename, start, length)
            if "-nostdin" not in args:
                args = ["-nostdin", *args]
            process = s.create_ffmpeg_process(*args)
            yield from s.chunked_ffmpeg_process(process)
            return
        stream = s._chunked_libav_section(filename, start, length)
        yield from map(bytes, s.equal_chunk_stream(stream, 3840))

    # Sort by when each note is played
    note_infos = sorted(note_infos, key=lambda info: info["time"])

    # Mapping between note types (A5, F#3) to note indices (69, 42)
    note_indices = s.make_indices_dict()
    note_indices["c8"] = note_indices["b7"] + 1  # Sometimes is a sample note

    # Helper function for getting each note's sound
    def sound_for(note_info):
        instrument = note_info["instrument"]
        note_index = note_indices[note_info["type"].lower()]
        if 13 <= instrument <= 16:
            # 13=sine, 14=square, 15=sawtooth, 16=triangle
            # Ignored because I'm too lazy to find their actual volume
            return s.passed(0)
        # Skip unknown instruments
        if instrument >= len(settings["volume"]):
            return s.passed(0)
        # Skip the custom synth
        if instrument == 55:
            return s.passed(0)
        length = note_info["length"]
        fade_time = 0
        if str(instrument) in settings.get("kSampleMap", ()):
            fade_time = 0.25  # Sounds close enough
        if str(instrument) in settings.get("fadeTimes", ()):
            fade_time = settings["fadeTimes"][str(instrument)]
        detune = 0
        if str(instrument) in settings.get("kSampleMap", ()):
            # Skip sampled instruments if soundit can't resample
            if not hasattr(s, "_resample_linear"):
                return s.passed(0)
            sample_notes = settings["kSampleMap"][str(instrument)]
            if note_info["type"] in sample_notes:
                note_index = sample_notes.index(note_info["type"])
            else:
                sample_note = min(sample_notes, key=lambda sample_note: (
                    abs(note_index - note_indices[sample_note.lower()])
                ))
                # Positive means sample is too low, negative means too high
                semitones_off = note_index - note_indices[sample_note.lower()]
                # We want to resample more frequently if too high, vice versa
                note_index = sample_notes.index(sample_note)
                detune += semitones_off*100
        sound = instrument_sound_at(
            instrument,
            note_index,
        )
        volume = settings["volume"][instrument] * note_info["volume"]
        if volume != 1:
            sound = s.volume(volume, sound)
        if detune != 0:
            sound = s._resample_linear(2**(detune/100/12), sound)
        if fade_time != 0:
            sound = s.cut(length + fade_time, sound)
            sound = s.fade(sound, fadein=0, fadeout=fade_time)
        return sound

    # Create notes of the form (info, length). Note that length is how many
    # seconds later the next node should start playing.
    def _notes_generator(note_infos):
        last_time = -9e999
        for note_info in note_infos:
            if last_time != note_info["time"]:
                if last_time != -9e999:
                    yield (None, note_info["time"] - last_time)
                last_time = note_info["time"]
            yield (note_info, 0)

    # Stable enough for our use (and also supports numpy)
    return s._notes_to_sound(
        _notes_generator(note_infos),
        lambda note_info, _: sound_for(note_info),
    )

parser = argparse.ArgumentParser(
    description="Generates PCM 16-bit 48kHz sound from note infos in stdin.",
)
parser.add_argument(
    "--settings",
    default="oscollection/settings.json",
    help="path to Online Sequencer settings JSON file",
)
parser.add_argument(
    "--template",
    default="oscollection/<>.ogg",
    help="template to Online Sequencer audio files",
)

if __name__ == "__main__":
    args = parser.parse_args()
    with open(args.settings) as file:
        settings = json.load(file)
    infos = json.load(sys.stdin)
    chunks = make_chunks(
        infos,
        settings=settings,
        template=args.template,
    )
    for chunk in chunks:
        sys.stdout.buffer.write(chunk)
