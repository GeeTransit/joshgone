import argparse
import sys
import json
import inspect

import soundit as s
import jsonfast as jf

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
            sample_lengths = settings.get("getSamplerTimePerNote")
            if sample_lengths is not None:
                if str(instrument) in sample_lengths:
                    length = sample_lengths[str(instrument)]
                elif "-1" in sample_lengths:
                    length = sample_lengths["-1"]
            start = note_index * length
        length -= 0.005  # Some files have noise at the end
        if not getattr(s, "has_av", False) or not hasattr(s, "file_chunks"):
            args = s.make_ffmpeg_section_args(filename, start, length)
            if "-nostdin" not in args:
                args = ["-nostdin", *args]
            process = s.create_ffmpeg_process(*args)
            try:
                yield from s.chunked_ffmpeg_process(process)
            except RuntimeError as e:
                # Older versions don't shut down the process properly
                if (
                    not hasattr(s, "_notes_to_sound")
                    and "process ended" not in e.args[0]
                ):
                    raise
            return
        stream = s._chunked_libav_section(filename, start, length)
        yield from map(bytes, s.equal_chunk_stream(stream, 3840))

    # Keep first note info (has metadata about song)
    note_infos = iter(note_infos)
    first_note_info = next(note_infos, None)

    # Ensure note times are increasing
    if first_note_info and first_note_info.get("sorted"):
        def _ensure_increasing_note_time(note_infos):
            yield first_note_info
            last_time = first_note_info["time"]
            for i, note_info in enumerate(note_infos):
                if note_info["time"] < last_time:
                    raise ValueError(f'note info is not sorted: {i}')
                yield note_info
                last_time = note_info["time"]
        note_infos = _ensure_increasing_note_time(note_infos)
    # Sort by when each note is played
    else:
        all_note_infos = []
        if first_note_info is not None:
            note_infos.append(first_note_info)
        all_note_infos.extend(note_infos)
        note_infos = sorted(note_infos, key=lambda info: info["time"])

    # Mapping between note types (A5, F#3) to note indices (69, 42)
    note_indices = s.make_indices_dict()
    note_indices["c8"] = note_indices["b7"] + 1  # Sometimes is a sample note

    # Helper function for getting each note's sound
    def sound_for(note_info):
        instrument = note_info["instrument"] % 10000
        note_index = note_indices[note_info["type"].lower()]
        if 13 <= instrument <= 16:
            return synth_sound_for(note_info)
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
        detune = note_info.get("detune", 0)
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

    # Mapping from note types to frequencies
    frequencies = s.make_frequencies_dict()

    synths_take_seconds = "seconds" in inspect.signature(s.sine).parameters
    def synth_sound_for(note_info):
        # 13=sine, 14=square, 15=sawtooth, 16=triangle
        instrument = note_info["instrument"] % 10000
        assert 13 <= instrument <= 16
        note_index = note_indices[note_info["type"].lower()]
        length = note_info["length"] + 0.005
        detune = note_info.get("detune", 0)

        # Note that two synths with the same frequency playing together
        # have twice the volume (in OSeq it's the same volume). Also note
        # that we fade at the end of each note (in OSeq the synth keeps
        # playing if there's a note afterwards but sometimes it makes a pop
        # sound).
        freq = frequencies[note_index - settings["min"][instrument]]
        if detune != 0:
            freq *= 2**(detune/100/12)
        func = (s.sine, s.square, s.sawtooth, s.triangle)[instrument - 13]
        if synths_take_seconds:
            sound = func(freq, seconds=length)
        else:  # Newer soundit versions don't have the seconds arg
            sound = s.cut(length, func(freq))

        volume = settings["volume"][instrument] * note_info["volume"]
        if instrument == 14:
            # Square waves are between -0.5 and 0.5 in OSeq
            volume *= 0.5
        if volume != 1:
            sound = s.volume(volume, sound)

        return s.fade(sound)

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

    if hasattr(s, "_notes_to_sound"):
        # Stable enough for our use (and also supports numpy)
        notes_to_sound = s._notes_to_sound
    else:
        # Older versions don't play after the last note
        def _layer_until_empty(note_infos, func):
            sounds = yield from s._layer(note_infos, func)
            while sounds:
                result = 0
                remove = []
                for sound in sounds:
                    try:
                        result += next(sound)
                    except StopIteration:
                        remove.append(sound)
                for sound in remove:
                    sounds.remove(sound)
                yield result
        notes_to_sound = _layer_until_empty

    return notes_to_sound(
        _notes_generator(note_infos),
        lambda note_info, _: sound_for(note_info),
    )

def _stream_read_json_array(next_func):
    # Calls next_func for more bytes from the stream, should return empty
    # bytes on EOF. Yields elements of an array.
    data = bytearray()
    chars = next_func()
    data += chars
    i = 0
    def recall(read_func):
        nonlocal i
        while True:
            try:
                return read_func()
            except (IndexError, ValueError):
                chars = next_func()
                if not chars:
                    raise ValueError("unexpected EOF while parsing JSON")
                del data[:i]
                i = 0
                data.extend(chars)
    i, first_char = recall(lambda: jf.read_tag(data, i))
    if first_char != b"["[0]:
        raise ValueError("expected JSON note infos")
    _, first_char = recall(lambda: jf.read_tag(data, i))
    if first_char == b"]"[0]:
        return
    while True:
        j, first_char, start = recall(lambda: jf.read(data, i))
        assert first_char not in b",]", first_char
        yield json.loads(data[i:j].decode())
        i = j
        i, split_char = recall(lambda: jf.read_tag(data, i))
        assert split_char in b",:]}", split_char
        if split_char == b"]"[0]:
            break

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
    infos = _stream_read_json_array(lambda: sys.stdin.buffer.read(2048))
    chunks = make_chunks(
        infos,
        settings=settings,
        template=args.template,
    )
    for chunk in chunks:
        sys.stdout.buffer.write(chunk)
