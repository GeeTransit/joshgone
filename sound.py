"""Synthesize music

This module uses iterators to represent audio streams. These iterators return
float values between [-1.0, 1.0) and can be chained, averaged, and precomputed
to your heart's content to create music. We call these iterators "sounds".

Note that all sounds are in 48kHz.

There is also a kinda sus music parser which can aid in creating longer music.
More info on that can be found in the music_to_notes's docstring.

Sound generators:
    sine
    silence
    piano  (requires init_piano to be called)

Sound effects:
    fade
    volume
    cut
    pad
    exact

Music functions:
    split_music
    music_to_notes
    notes_to_sine
    _layer  (unfinalized API)

A very simple example: (Note that ctx is a discord.Context)

    import sound as s
    await s.play_source(
        ctx.voice_client,
        s.IteratorSource(s.chunk(s.sine(440, seconds=1))),
    )

A longer example:

    import itertools
    import sound as s

    indices = s.make_indices_dict()
    frequencies = s.make_frequencies_dict()
    notes = "a3 c e a g e c e d e d c a3 c a3 g3".split()

    await s.play_source(
        ctx.voice_client,
        s.IteratorSource(s.chunk(itertools.chain.from_iterable(
            s.sine(frequencies[indices[note]], seconds=0.5)
            for note in notes
        ))),
    )

An even longer example:

    import sound as s
    s.init_piano()

    indices = s.make_indices_dict("do di re ri mi fa fi so si la li ti".split())
    music = '''
        . mi mi mi
        fa do . do
        . so mi do
        re mi,re - mi
    '''

    await s.play_source(
        ctx.voice_client,
        s.IteratorSource(s.chunk(
            s.scale(2, s._layer(
                s.music_to_notes(music, line_length=1.15),
                lambda name, length: s.piano(indices[name] + 1),
            ))
        )),
    )

There is also some builtin music that are prefixed with MUSIC_, such as
MUSIC_DIGITIZED, provided for testing purposes.

"""
import asyncio
import math
import discord


# - Constants

RATE = 48000  # 48kHz
A4_FREQUENCY = 440
A4_INDEX = 57
NOTE_NAMES = "c c# d d# e f f# g g# a a# b".split()


# - Sound generators

def silence(*, seconds=1):
    """Returns 0 for the specified amount of time"""
    for _ in range(int(seconds * RATE)):
        yield 0

def sine(freq=A4_FREQUENCY, *, seconds=1):
    """Returns a sine wave at freq for the specified amount of time"""
    for x in range(int(seconds * RATE)):
        yield math.sin(2*math.pi * freq * (x/RATE))
sine_wave = sine  # Old name

piano_data = None
def init_piano():
    """Loads the piano sound for use

    The raw file 0.raw was generated from Online Sequencer's Electric Piano
    instrument (from https://onlinesequencer.net/app/instruments/0.ogg?v=12)
    and FFmpeg was then used to convert it into a raw mono 48kHz signed 16-bit
    little endian file (using ffmpeg -i 0.ogg -f s16le -acodec pcm_s16le -ac 1
    -ar 48000 0.raw).

    """
    global piano_data
    if piano_data is not None:
        return
    with open("0.raw", "rb") as f:
        piano_data = f.read()

def piano(index=A4_INDEX, *, seconds=1):
    """Returns a piano sound at index

    Note that passing a time is now deprecated. Wrap exact around this instead.

    If the length of time is shorter than a second, it will be cut off.
    If the length of time is longer than a second, silence will be added.

    """
    index -= 2*12  # The piano starts at C2
    for i in range(index * RATE*2, int((index+min(seconds, 1)) * RATE*2), 2):
        yield int.from_bytes(piano_data[i:i+2], "little", signed=True) / (1<<16-1)
    if seconds > 1:
        yield from silence(seconds=seconds-1)


# - Sound effects

def fade(iterator, /, *, fadein=0.005, fadeout=0.005):
    """Fades in and out of the sound

    If the sound is less than fadein+fadeout seconds, the time between fading
    in and fading out is split proportionally.

    """
    fadein = int(fadein * RATE)
    fadeout = int(fadeout * RATE)
    last = []
    try:
        while len(last) < fadein + fadeout:
            last.append(next(iterator))
    except StopIteration as e:
        split = int(len(last) * fadein / (fadein+fadeout))
        for i in range(0, split):
            yield last[i] * ((i+1) / split)
        for i in range(split, len(last)):
            yield last[i] * ((len(last)-i) / (len(last)-split))
        return e.value
    for i in range(0, fadein):
        yield last[i] * ((i+1) / fadein)
    del last[:fadein]
    assert len(last) == fadeout
    insert = 0
    try:
        while True:
            value = last[insert]
            last[insert] = next(iterator)
            yield value
            insert = (insert + 1) % fadeout
    except StopIteration as e:
        for i, j in enumerate(range(insert - fadeout, insert)):
            yield last[j] * ((fadeout-i) / fadeout)
        return e.value

def both(iterator, /):
    """Deprecated. sound.chunk accepts floats"""
    for num in iterator:
        yield num, num

def volume(factor, iterator, /):
    """Multiplies each point by the specified factor"""
    for num in iterator:
        yield num * factor
scale = volume  # Old name

def cut(seconds, sound, /):
    """Ends the sound after the specified time"""
    for _ in range(int(seconds * RATE)):
        yield next(sound)

def pad(seconds, sound, /):
    """Pads the sound with silence if shorter than the specified time"""
    points = 0
    while True:
        try:
            yield next(sound)
        except StopIteration:
            break
        else:
            points += 1
    if points < int(seconds * RATE):
        yield from silence(seconds=seconds - points/RATE)

def exact(seconds, sound, /):
    """Cuts or pads the sound to make it exactly the specified time"""
    return (yield from cut(pad(seconds, sound)))


# - Utility for audio sources

async def play_source(voice_client, source):
    """Plays and waits until the source finishes playing"""
    future = asyncio.Future()
    def after(exc):
        if exc is None:
            future.set_result(None)
        else:
            future.set_exception(exc)
    voice_client.play(source, after=after)
    await future
    return future.result()

class IteratorSource(discord.AudioSource):
    """Wraps an iterator of bytes into an audio source

    Usage:
        # returns an audio source implementing discord.AudioSource
        source = s.IteratorSource(s.chunk(s.sine(440, seconds=1)))
        ctx.voice_client.play(source, after=lambda _: print("finished"))

    """
    def __init__(self, iterator, *, is_opus=False):
        self._iterator = iterator
        self._is_opus = is_opus

    def is_opus(self):
        return self._is_opus

    def cleanup(self):
        try:
            self._iterator.close()
        except AttributeError:
            pass
        self._iterator = None

    def read(self):
        try:
            return next(self._iterator)
        except StopIteration:
            return b""

def chunk(iterator, /):
    """Converts a stream of floats or two-tuples of floats in [-1, 1) to bytes

    This is hardcoded to return 20ms chunks of signed 16-bit little endian
    stereo 48kHz audio.

    If the iterator returns a single float, it will have both sides play the
    same point.

    If the iterator doesn't complete on a chunk border, null bytes will be
    added until it reaches the required length, which should be 3840 bytes.

    """
    volume = 1<<15 - 1  # 16-bit
    rate = 48000  # 48kHz
    chunks_per_second = 1000//20  # 20ms
    points_per_chunk = rate//chunks_per_second
    size = points_per_chunk * 2 * 2  # 16-bit stereo
    current = bytearray()
    for num in iterator:
        if type(num) is tuple:
            left, right = num
        else:
            left = right = num
        current += int(volume * left).to_bytes(2, "little", signed=True)
        current += int(volume * right).to_bytes(2, "little", signed=True)
        if len(current) >= size:
            yield bytes(current)
            current.clear()
    if current:
        while not len(current) >= size:
            current += b"\x00\x00\x00\x00"
        yield bytes(current)


# - Utility for note names and the like

def make_frequencies_dict(*, a4=A4_FREQUENCY, offset=0):
    """Makes a dictionary containing frequencies for each note

     - a4 is the frequency for the A above middle C
     - names is a list of note names
     - offset is the number of semitones to offset each note by

    """
    frequencies = {}
    for i in range(0, 8):
        for j in range(12):
            k = i*12 + j + offset
            frequency = a4 * 2**((k - A4_INDEX)/12)
            frequencies[k] = frequency
    return frequencies

def make_indices_dict(names=NOTE_NAMES, *, a4=57, offset=0):
    """Makes a dictionary containing indices of common note names

     - a4 is the index for the A above middle C
     - names is a list of note names
     - offset is the number of semitones to offset each note by

    """
    indices = {}
    for i in range(0, 8):
        for j, note in enumerate(names):
            k = i*len(names) + j + offset + (a4 - A4_INDEX)
            indices[f"{note}{i}"] = k
            if i == 4:
                indices[note] = k
    return indices


# - Utilities for converting music to notes to sounds

def music_to_notes(music, *, line_length=1):
    """Converts music into notes (two tuples of note name and length)

    This function returns a list of two-tuples of a string/None and a float.
    The first item is the note name (or a break if it is a None). The second
    item is its length.

    Note that there is a break between notes by default.

    A music string is first divided into lines with one line being the
    specified length, defaulting to 1. Each line is then split by whitespace
    into parts with the length divided evenly between them. Each part is then
    split by commas "," into notes with the length again divided evenly between
    them.

    Empty lines or lines starting with a hash "#" are skipped.

    Note names can be almost anything. A note name of a dash "-" continues the
    previous note without a break between then. A suffix of a tilde "~" removes
    the break after the note, whereas an exclamation point "!" adds one.

    """
    processed = []
    for line in music.splitlines():
        line = line.strip()
        if line == "":
            continue
        if line.startswith("#"):
            continue
        parts = line.split()
        for part in parts:
            part_length = line_length / len(parts)
            notes = part.split(",")
            for note in notes:
                note_length = part_length / len(notes)
                flags = ""
                if note.endswith("~"):
                    note = note.removesuffix("~")
                    flags += "~"
                elif note.endswith("!"):
                    note = note.removesuffix("!")
                    flags += "!"
                processed.append((note, flags, note_length))
    notes = []
    last_note = "."
    for i, (note, flags, note_length) in enumerate(processed):
        has_silence = True
        if i+1 < len(processed) and processed[i+1][0] == "-":
            has_silence = False
        if "~" in flags:
            has_silence = False
        if "!" in flags:
            has_silence = True
        if note == "-":
            note = last_note
        silent_length = 0
        if has_silence:
            silent_length = min(0.1, 0.25*note_length)
            note_length -= silent_length
        if note == ".":
            silent_length += note_length
            note_length = 0
        if note_length > 0:
            if len(notes) > 0 and notes[-1][0] == note:
                notes[-1] = (note, notes[-1][1] + note_length)
            else:
                notes.append((note, note_length))
        if silent_length > 0:
            notes.append((None, silent_length))
        last_note = note
    return notes
music_to_sounds = music_to_notes  # Old name

def split_music(music):
    r"""Splits music into individual sequences

    Lines starting with a slash "/" will be added to a new sequence. All other
    lines (including blanks and comments) will be part of the main sequence.

    Usage:
        split_music("1\n1") == ["1\n1"]
        split_music("1\n/2\n1") == ["1\n1", "2"]
        split_music("1\n/2\n/3\n1\n/2") == ["1\n1 ", "2\n2", "3"]

    """
    sequences = [[]]
    sequence_number = 0
    for line in music.splitlines():
        if line.strip().startswith("/"):
            sequence_number += 1
            _, _, line = line.partition("/")
        else:
            sequence_number = 0
        while not len(sequences) > sequence_number:
            sequences.append([])
        sequences[sequence_number].append(line)
    for i, sequence in enumerate(sequences):
        sequences[i] = "\n".join(sequence)
    return sequences

def notes_to_sine(notes, frequencies, *, line_length=1):
    """Converts notes into sine waves

     - notes is an iterator of two-tuples of note names/None and lengths
     - frequencies is a dict to look up the frequency for each note name
     - line_length is how much to scale the note by

    """
    for note, length in notes:
        length *= line_length
        if note is not None:
            yield from sine(freq=frequencies[note], seconds=length)
        else:
            yield from silence(seconds=length)
sounds_to_sine = notes_to_sine  # Old name

# Calls func on each note and plays them together. The sound returned from func
# can be longer than its length, in which case multiple sounds will be added
# together.
def _layer(notes, func, *, line_length=1):
    current = set()
    for note, length in notes:
        length *= line_length
        if note is not None:
            current.add(func(note, length))
        for _ in range(int(length * RATE)):
            result = 0
            remove = []
            for it in current:
                try:
                    result += next(it)
                except StopIteration:
                    remove.append(it)
            for it in remove:
                current.remove(it)
            yield result
    return current


# - Meta utilities

def reload():
    """Reloads this module. Helper function"""
    import sound
    import importlib
    importlib.reload(sound)


# - Builtin music

MUSIC_DIGITIZED = '''
# names="do di re ri mi fa fi so si la li ti".split()
# offset=1
# line_length=1.15

. mi mi mi
fa do . do
. so mi do
re mi,re - mi

la3 mi mi mi
fa do . do
. so mi do
re mi,re - mi

do mi mi mi
fa do . do
. so mi do
re mi,re - mi

la3 la3 la3 fa3
fa3 fa3 fa3 fa3
do do do so3
so3 so3 si3 si3

la3 la3 la3 fa3
fa3 fa3 fa3 fa3
do do do so3
la3,do,mi,so la,do5,mi5,so5 la5 .

do so mi do
re re,mi so mi
do so mi do
re re,mi so re

do so mi do
re re,mi so mi
do so mi do
re re,mi so re

- do . la3
. la3 do re
so3 do mi do
re do,re - do

- do . la3
. la3 do re
so3 do mi do
re do,re - do

do la3 - so3
do re,mi - re
. . do so3
re mi re do

. . do so3
fa mi,re - do
- so3 re do
mi so re do

la3 mi mi mi
fa do . do
. so mi do
re mi,re - mi

do mi mi mi
fa do . do
. so mi do
re mi,re - mi

la3 la3 la3 fa3
fa3 fa3 fa3 fa3
do do do so3
so3 so3 si3 si3

la3 la3 la3 fa3
fa3 fa3 fa3 fa3
do do do so3
la3,do,mi,so la,do5,mi5,so5 la5 .

do so mi do
re re,mi so mi
do so mi do
re re,mi so re

do so mi do
re re,mi so mi
do so mi do
re re,mi so re

- do . la3
. la3 do re
so3 do mi do
re do,re - do

- do . la3
. la3 do re
so3 do mi do
re do,re - -

do
'''

MUSIC_MEGALOVANIA = '''
# names="do di re ri mi fa fi so si la li ti".split()
# offset=6
# line_length=2.2

la3 la3 la - mi - - ri - re - do - la3 do re
so3 so3 la - mi - - ri - re - do - la3 do re
fi3 fi3 la - mi - - ri - re - do - la3 do re
fa3 fa3 la - mi - - ri - re - do - la3 do re

la3 la3 la - mi - - ri - re - do - la3 do re
so3 so3 la - mi - - ri - re - do - la3 do re
fi3 fi3 la - mi - - ri - re - do - la3 do re
fa3 fa3 la - mi - - ri - re - do - la3 do re

do - do do - do - do - la3 - la3 - - - -
do - do do - re - ri - re do la3 do re - -
do - do do - re - ri - mi - so - mi - -
la - la - la mi la so - - - - - - - -

mi - mi mi - mi - mi - re - re - - - -
mi - mi mi - mi - re - mi - so - mi re -
la do mi do so do mi do re do re mi so mi re do
la3 - ti3 - do la3 do so - - - - - - - -

la3 - - - - - - - do la3 do re ri re do la3
do la3 do - re - - - - - - - - - re mi
la - re mi re do ti3 la3 do - re - mi - so -
la - la - la mi la so - - - - - - - -

do - re - mi - do5 - ti - - - si - - -
ti - - - do5 - - - re5 - - - ti - - -
mi5 - - - - - - - mi5 ti so re do ti3 la3 si3
so3 - - - - - - - si3 - - - - - - -

mi3 - - - - - - - - - - - do - - -
ti3 - - - - - - - si3 - - - - - - -
la3
-
'''
