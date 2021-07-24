"""Synthesize music

This module uses iterators to represent audio streams. These iterators return
float values between [-1.0, 1.0) and can be chained, averaged, and precomputed
to your heart's content to create music. We call these iterators "sounds".

Note that all sounds are in 48kHz.

There is also a kinda sus music parser which can aid in creating longer music.
More info on that can be found in the music_to_notes's docstring.

Sound generators:
    sine
    square
    sawtooth
    triangle
    silence
    piano  (requires init_piano to be called)

Sound creation utilities:
    passed

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

Audio source utilities:
    chunked
    unchunked

discord.py utilities:
    wrap_discord_source
    unwrap_discord_source
    play_discord_source

FFmpeg utilities:
    create_ffmpeg_process
    chunked_ffmpeg_process

A very simple example: (Note that ctx is a discord.Context)

    import sound as s
    await s.play_discord_source(
        ctx.voice_client,
        s.wrap_discord_source(s.chunked(s.sine(440, seconds=1))),
    )

A longer example:

    import itertools
    import sound as s

    indices = s.make_indices_dict()
    frequencies = s.make_frequencies_dict()
    notes = "a3 c e a g e c e d e d c a3 c a3 g3".split()

    await s.play_discord_source(
        ctx.voice_client,
        s.wrap_discord_source(s.chunked(itertools.chain.from_iterable(
            s.sine(frequencies[indices[note]], seconds=0.5)
            for note in notes
        ))),
    )

An even longer example:

    import sound as s
    s.init_piano()

    names = "do di re ri mi fa fi so si la li ti".split()
    indices = s.make_indices_dict(names)
    music = '''
        . mi mi mi
        fa do . do
        . so mi do
        re mi,re - mi
    '''

    await s.play_discord_source(
        ctx.voice_client,
        s.wrap_discord_source(s.chunked(
            s.volume(2, s._layer(
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
import json
import itertools
import functools
import subprocess
import copy

try:
    import discord
except ImportError:
    has_discord = False
else:
    has_discord = True

# - Constants

RATE = 48000  # 48kHz
A4_FREQUENCY = 440
A4_INDEX = 57
NOTE_NAMES = "c c# d d# e f f# g g# a a# b".split()


# - Sound generators

def silence(*, seconds=1):
    """Returns silence for the specified amount of time"""
    for _ in passed(seconds):
        yield 0

def sine(freq=A4_FREQUENCY, *, seconds=1):
    """Returns a sine wave at freq for the specified amount of time"""
    for x in passed(seconds):
        yield math.sin(2*math.pi * freq * x)
sine_wave = sine  # Old name

def square(freq=A4_FREQUENCY, *, seconds=1):
    """Returns a square wave at freq for the specified amount of time"""
    for x in passed(seconds):
        yield (freq*x % 1 > 0.5) * 2 - 1

def sawtooth(freq=A4_FREQUENCY, *, seconds=1):
    """Returns a sawtooth wave at freq for the specified amount of time"""
    for x in passed(seconds):
        yield ((freq*x + 0.5) % 1 - 0.5) * 2

def triangle(freq=A4_FREQUENCY, *, seconds=1):
    """Returns a triangle wave at freq for the specified amount of time"""
    for x in passed(seconds):
        yield (-abs(-((freq*x + freq/2)%1) + 0.5) + 0.25) * 4

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
    for x in passed(min(seconds, 1)):
        i = int((index + x) * RATE + 0.5) * 2
        yield int.from_bytes(piano_data[i:i+2], "little", signed=True) / (1<<16-1)
    if seconds > 1:
        yield from silence(seconds=seconds-1)


# - Experimental sounds from Online Sequencer

class _OSInstrument:
    """An instrument wrapping a collection of sounds

    These sounds are taken from Online Sequencer. The audio is from links of
    the form `https://onlinesequencer.net/app/instruments/<>.ogg?v=12` with
    `<>` being replaced with the instrument number. The settings are from
    `https://onlinesequencer.net/resources/c/85dda66875c37703d44f50da0bb85185.js`.

    Online Sequencer's lowest note index (0) represents a C2, which would be 24
    according to make_indices_dict. All note indices are offset accordingly.

    Sounds are cached on a per instrument basis with the instrument instance
    and note index as the key. You can pass your own cache if necessary. Note
    that we cache the binary data, not the floats, as this reduces memory usage
    by a lot (at the cost of some more CPU usage).

    Note that no FFmpeg preprocessing is needed; all reencoding is done at
    runtime. However, you can still specify a raw PCM file. Just also pass
    the relevant FFmpeg options specifying the format, sample rate, and number
    of channels. For 48 kHz signed 16-bit little endian mono audio, you'd pass
    `before_options=["-f", "s16le", "-ar", "48000", "-ac", "1"]`. You may also
    want to pass `options=["-v", "error"]` to make FFmpeg quieter (it warns you
    about estimating the duration from the bitrate).

    """
    _SETTINGS_FILENAME = "onlinesequencer_settings.json"
    _INSTRUMENT_FILENAME = "./_ossounds/<>.ogg"
    _INDEX_OFFSET = 2 * 12

    _settings = None

    def __init__(
        self,
        instrument,
        *,
        filename=None,
        before_options=None,
        options=None,
        cache=None,
        max_cache_size=128,
    ):
        """Create an instrument

        If the instrument is a string, it is looked up and converted into an
        instrument number.

        The filename can optionally have a pair of angle brackets `<>` which
        will be replaced by the instrument number.

        The before_options and options arguments are included in the
        .ffmpeg_args_for method's return value. Note that they will be prefixed
        by `["-ss", str(start_time)]` for before_options and
        `["-t", str(self.seconds)]` for options.

        For the sound cache, you can directly pass an LRUIterableCache to the
        cache keyword argument. Passing max_cache_size is deprecated.

        """
        # Load settings
        self.load_settings()
        if type(instrument) is str:
            instrument = self._settings["instruments"].index(instrument)
        # Store them on the instrument
        self.instrument = instrument
        self.instrument_name = self._settings["instruments"][instrument]
        self.min = self._settings["min"][instrument] + self._INDEX_OFFSET
        self.max = self._settings["max"][instrument] + self._INDEX_OFFSET
        self.original_bpm = self._settings["originalBpm"][instrument] * 2
        self.seconds = 60 / self.original_bpm
        # Get filename from template if one wasn't provided
        if filename is None:
            filename = self._INSTRUMENT_FILENAME
        filename = filename.replace("<>", str(instrument))
        filename = filename.replace("{i}", str(instrument))  # Old template
        # FFmpeg options
        self.filename = filename
        self.before_options = before_options
        self.options = options
        # Create the cache for source iterators
        if cache is None:
            cache = LRUIterableCache(maxsize=max_cache_size)
        self.cache = cache

    # Simple hash (we compare instruments by identity)
    def __hash__(self):
        return hash(id(self))

    def at(self, index=A4_INDEX):
        """Returns a sound at the specified note index

        Note that the source iterable may be cached. Thus, if the file changes,
        the returned sounds may not be updated. Use .cache_clear() to refresh
        the cache.

        """
        # If the index is out of range, return an empty sound (no points)
        start = self.start_of(index)
        if start is None:
            return
        # Check the cache before getting the chunks
        key = (self, index)
        chunks = self.cache.get(key, lambda: self._chunks_at(start))
        # Unchunk and convert into a sound
        yield from ((x+y)/2 for x, y in unchunked(chunks))

    def start_of(self, index=A4_INDEX):
        """Returns the start time for the specified note or None if invalid"""
        # If the index is out of range, return None
        if not self.min <= index <= self.max:
            return None
        # Return the starting time otherwise
        return (index - self.min) * self.seconds

    def ffmpeg_args_for(self, start, *, before_options=None, options=None):
        """Returns a list of arguments to FFmpeg

        It will take the required amount of audio starting from the specified
        start time and convert them into PCM 16-bit stereo audio to be piped to
        stdout.

        The instance's .before_options will be added before the before_options
        argument and likewise with .options.

        """
        if start is None:
            raise ValueError("start must be a float")
        if (
            isinstance(self.before_options, str)
            or isinstance(self.options, str)
            or isinstance(before_options, str)
            or isinstance(options, str)
        ):
            # Strings are naughty. Force user to split them beforehand
            raise ValueError("FFmpeg options should be lists, not strings")
        return [
            "-ss", str(start),
            *(self.before_options or ()),
            *(before_options or ()),
            "-i", self.filename,
            "-f", "s16le",
            "-ar", "48000",
            "-ac", "2",
            "-loglevel", "warning",
            "-t", str(self.seconds),
            *(self.options or ()),
            *(options or ()),
            "pipe:1",
        ]

    @classmethod
    def load_settings(cls, *, force=False):
        if not force and cls._settings is not None:
            return False
        with open(cls._SETTINGS_FILENAME) as file:
            cls._settings = json.load(file)
        return True

    def _chunks_at(self, start):
        # Get FFmpeg arguments
        args = self.ffmpeg_args_for(start)
        # Create the process
        process = create_ffmpeg_process(*args)
        # Create a chunks from the process
        return chunked_ffmpeg_process(process)

    def cache_clear(self):
        """Clears the source iterables cache

        Same as doing .cache.clear().

        """
        self.cache.clear()

# FFmpeg is now part of _OSInstrument
_OSInstrumentFFmpeg = _OSInstrument

# Caching is now part of _OSInstrumentFFmpeg
_OSInstrumentFFmpegCached = _OSInstrumentFFmpeg

# - LRU cache

class LRUCache:
    """An LRU cache

    The maxsize argument specifies the maximum size the cache can grow to.
    Specifying 0 means that the cache will remain empty. Specifying None means
    the cache will grow without bound.

    To get a value, call .get with a key (to uniquely identify each value, and
    with a zero-argument function that returns a value for when it doesn't
    exist.

    To clear the cache and reset the hits / misses counters, call .clear().

    To change the maxsize, set the .maxsize property to its new value. Note
    that it won't take effect until the next .get call with a key not in the
    cache. It is not recommended, but you can call ._ensure_size() to force
    it to resize the cache.

    For info on the number of hits / misses, check the .hits and .misses
    attributes. You can reset them to 0 manually if you'd like.

    Checking and modifying the cache manually isn't recommended, but they are
    available through the .results attribute. It stores a dictionary between
    keys and values. You can clear them manually if you'd like.

    """
    def __init__(self, *, maxsize=128):
        # Set cache state
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0
        self.results = {}

    def get(self, key, value_func):
        """Return the value for this key, calling value_func if needed"""
        # If the key ain't in the cache...
        if key not in self.results:
            # Get the value from calling the function
            value = value_func()
            # Update cache with the value
            result = self._miss(key, value)
            # Ensure the cache's size isn't over self.maxsize
            self._ensure_size()

        # If the key is in the cache...
        else:
            # Get the cached value
            result = self._hit(key)

        # Return the value
        return result

    def clear(self):
        """Clears the cache and the hits / misses counters"""
        self.hits = 0
        self.misses = 0
        self.results.clear()

    def __repr__(self):
        maxsize = self.maxsize
        hits = self.hits
        misses = self.misses
        return f"<{type(self).__name__} {maxsize=} {hits=} {misses=}>"

    def _miss(self, key, value):
        # Note down that we missed it
        self.misses += 1
        # Update cache with the value
        result = self.results[key] = value
        # Return the value
        return result

    def _hit(self, key):
        # Note down that we hit it
        self.hits += 1
        # Move key to the end of the dict (LRU cache)
        result = self.results.pop(key)
        self.results[key] = result
        # Return the value
        return result

    def _ensure_size(self):
        if self.maxsize is None:  # Cache is not unbounded
            return False
        if len(self.results) <= max(0, self.maxsize):
            return False
        # Fast path for maxsize of 0 (clear everything)
        if self.maxsize == 0:
            self.results.clear()
            return True
        # Get old keys in the cache (order is kept in a dict)
        old_keys = list(itertools.islice(
            iter(self.results.keys()),
            len(self.results) - self.maxsize,
        ))
        # Remove old keys
        for old_key in old_keys:
            self.results.pop(old_key)
        # Force a resizing of the dictionary (resize on inserts)
        self.results[1] = 1
        del self.results[1]
        return True

# - LRU cache for iterators

class LRUIterableCache(LRUCache):
    """An LRU cache for iterables

    This class internally stores itertools.tee objects wrapped around the
    original values and returns copy.copy(...) of the tees in the cache.

    We use tee objects for a few reasons:
        1. They can be iterated at different speeds.
        2. They are iterators (lazily evaluated).
        3. They can be copied (major orz for this one).
        4. They are fast (implemented in C).

    A .get() call first finds a tee object, using the cached tee if one exists,
    or creating a fresh one using the iterable_func. We then make a copy of the
    tee to keep the original unchanged.

    See LRUCache for more info on caching. See itertools.tee for more info on
    tee objects.

    """
    def get(self, key, iterable_func):
        """Return the iterator for this key, calling iterable_func if needed"""
        value_func = lambda: itertools.tee(iterable_func(), 1)[0]
        return copy.copy(super().get(key, value_func))

def lru_iter_cache(func=None, *, maxsize=128):
    """Decorator to wrap a function returning iterables

    If maxsize is 0, no caching will be done. If maxsize is None, the cache
    will be unbounded.

    See LRUIterableCache for more info.

    """
    if func is None:
        return functools.partial(lru_iter_cache, maxsize=maxsize)

    # Create the cache instance
    cache = LRUIterableCache(maxsize=maxsize)

    # Wrap the original function
    @functools.wraps(func)
    def _lru_iter_cache_wrapper(*args, **kwargs):
        # The key must not be the same for different call args / kwargs.
        # Example: f("a", 1) vs f(a=1).
        key = (args, *kwargs.items())
        iterable_func = lambda: func(*args, **kwargs)
        return cache.get(key, iterable_func)

    # Add the cache to the function object for later introspection
    _lru_iter_cache_wrapper.cache = cache
    _lru_iter_cache_wrapper.cache_clear = cache.clear

    # Return the wrapper function
    return _lru_iter_cache_wrapper

# - FFmpeg utilities

def create_ffmpeg_process(
    *args,
    executable="ffmpeg",
    pipe_stdin=False,
    pipe_stdout=True,
    pipe_stderr=False,
    **kwargs,
):
    """Creates a process that run FFmpeg with the given arguments

    This assumes that ffmpeg.exe is on your PATH environment variable. If not,
    you can specify its location using the executable argument.

    For the pipe_* arguments, if it is True, subprocess.PIPE will be passed to
    subprocess.Popen's constructor. Otherwise, None will be passed.

    All other keyword arguments, are passed directly to subprocess.Popen.

    """
    subprocess_kwargs = {
        "stdin": subprocess.PIPE if pipe_stdin else None,
        "stdout": subprocess.PIPE if pipe_stdout else None,
        "stderr": subprocess.PIPE if pipe_stderr else None,
    }
    subprocess_kwargs.update(kwargs)
    return subprocess.Popen([executable, *args], **subprocess_kwargs)
process_from_ffmpeg_args = create_ffmpeg_process  # Old name

def chunked_ffmpeg_process(process):
    """Returns an iterator of chunks from the given process

    This function is hardcoded to take PCM 16-bit stereo audio, same as the
    chunked function. See that function for more info.

    """
    SAMPLING_RATE = 48000  # 48kHz
    CHANNELS = 2  # stereo
    SAMPLE_WIDTH = 2 * 8  # 16-bit
    FRAME_LENGTH = 20  # 20ms

    SAMPLE_SIZE = SAMPLE_WIDTH * CHANNELS
    SAMPLES_PER_FRAME = SAMPLING_RATE * FRAME_LENGTH // 1000
    FRAME_SIZE = SAMPLES_PER_FRAME * SAMPLE_SIZE
    FRAME_SIZE_BYTES = FRAME_SIZE // 8

    try:
        read = process.stdout.read  # speedup by removing a getattr
        while data := read(FRAME_SIZE_BYTES):
            yield data

    finally:
        process.kill()
        if process.poll() is None:
            process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                "process ended with a nonzero return code:"
                f" {process.returncode}"
            )
iterator_from_process = chunked_ffmpeg_process  # Old name

# - Experimental OS sound functions

_onlinesequencer_data = {}
_onlinesequencer_settings = None

def _init_onlinesequencer_sound(instrument):
    assert type(instrument) is int
    if instrument in _onlinesequencer_data:
        return
    _onlinesequencer_data[instrument] = _OSInstrument(
        instrument,
        filename=f"<>.raw",
        before_options="-f s16le -ar 48000 -ac 1".split(),
        options="-v error".split(),
    )

def _init_onlinesequencer_settings():
    _OSInstrument.load_settings()

def _onlinesequencer_sound(instrument, index=A4_INDEX):
    return (yield from _onlinesequencer_data[instrument].at(index))


# - Sound creation utilities

def passed(seconds=1):
    """Returns a sound lasting the specified time yielding the seconds passed

    This abstracts away the use of RATE to calculate the number of points.

    If seconds is None, the retured sound will be unbounded.

    """
    if seconds is None:
        iterator = itertools.count()
    else:
        iterator = range(int(seconds * RATE))
    for i in iterator:
        yield i / RATE


# - Sound effects

def fade(iterator, /, *, fadein=0.005, fadeout=0.005):
    """Fades in and out of the sound

    If the sound is less than fadein + fadeout seconds, the time between fading
    in and fading out is split proportionally.

    """
    fadein = int(fadein * RATE)
    fadeout = int(fadeout * RATE)

    # First get fadein + fadeout samples
    last = []
    try:
        while len(last) < fadein + fadeout:
            last.append(next(iterator))
    except StopIteration as e:
        # If we ended early, split the fades equally between fadein and fadeout
        split = int(len(last) * fadein / (fadein+fadeout))
        for i in range(0, split):  # Fade in
            yield last[i] * ((i+1) / split)
        for i in range(split, len(last)):  # Fade out
            yield last[i] * ((len(last)-i) / (len(last)-split))
        return e.value
    # Yield the fadein part
    for i in range(0, fadein):
        yield last[i] * ((i+1) / fadein)
    # Remove the fadein
    del last[:fadein]
    assert len(last) == fadeout
    # Loop until the sound ends. We use the last list as a circular buffer with
    # the insert variable pointing to the next index to be overwritten.
    insert = 0
    try:
        while True:
            # Yield the oldest point and get the next point
            value = last[insert]
            last[insert] = next(iterator)
            yield value
            insert = (insert + 1) % fadeout
    except StopIteration as e:
        # Yield the fadeout
        for i, j in enumerate(range(insert - fadeout, insert)):
            yield last[j] * ((fadeout-i) / fadeout)
        return e.value

def both(iterator, /):
    """Deprecated. sound.chunked accepts floats"""
    for num in iterator:
        yield num, num

def volume(factor, sound, /):
    """Multiplies each point by the specified factor"""
    for num in sound:
        yield num * factor
scale = volume  # Old name

def cut(seconds, sound, /):
    """Ends the sound after the specified time"""
    for _ in range(int(seconds * RATE)):
        yield next(sound)

def pad(seconds, sound, /):
    """Pads the sound with silence if shorter than the specified time"""
    for x in passed(None):
        try:
            point = next(sound)
        except StopIteration:
            break
        else:
            yield point
    yield from silence(seconds=seconds - x)

def exact(seconds, sound, /):
    """Cuts or pads the sound to make it exactly the specified time"""
    return (yield from cut(seconds, pad(seconds, sound)))


# - Utility for audio sources

async def play_discord_source(voice_client, source):
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
play_source = play_discord_source  # Old name

if has_discord:
    # Make our class a subclass of discord.py AudioSource if possible
    class DiscordIteratorSource(discord.AudioSource):
        """Internal subclass of discord.py's AudioSource for iterators

        See wrap_discord_source for more info.

        """
        def __init__(self, iterator, *, is_opus=False):
            self._iterator = iterator
            self._is_opus = is_opus

        def is_opus(self):
            return self._is_opus

        def cleanup(self):
            try:
                close = self._iterator.close
            except AttributeError:
                pass
            else:
                close()
            self._iterator = None

        def read(self):
            try:
                return next(self._iterator)
            except StopIteration:
                return b""
    IteratorSource = DiscordIteratorSource  # Old name

def wrap_discord_source(iterator, /, *, is_opus=False):
    """Wraps an iterator of bytes into an audio source

    If is_opus is False (the default), the iterator must yield 20ms of signed
    16-bit little endian stereo 48kHz audio each iteration. If is_opus is True,
    the iterator should yield 20ms of Opus encoded audio each iteration.

    Usage:
        # returns an audio source implementing AudioSource
        source = s.wrap_discord_source(s.chunked(s.sine(440, seconds=1)))
        ctx.voice_client.play(source, after=lambda _: print("finished"))

    """
    if not has_discord:
        raise RuntimeError("discord.py needed to make discord.AudioSources")
    return DiscordIteratorSource(iterator, is_opus=is_opus)
iterator_to_source = wrap_discord_source  # Old name

def chunked(sound, /):
    """Converts a stream of floats or two-tuples of floats in [-1, 1) to bytes

    This is hardcoded to return 20ms chunks of signed 16-bit little endian
    stereo 48kHz audio.

    If the sound yield float instead of two-tuples, it will have both sides
    play the same point.

    If the sound doesn't complete on a chunk border, null bytes will be added
    until it reaches the required length, which should be 3840 bytes.

    Note that floats not in the range [-1, 1) will be silently truncated to
    fall inside the range. For example, 1.5 will be processed as 1 and -1.5
    will be processed as -1.

    """
    volume = 1 << (16-1)  # 16-bit signed
    high, low = volume-1, -volume  # allowed range
    rate = 48000  # 48kHz
    chunks_per_second = 1000//20  # 20ms
    points_per_chunk = rate//chunks_per_second
    size = points_per_chunk * 2 * 2  # 16-bit stereo
    int_to_bytes = int.to_bytes  # speedup by removing a getattr
    current = bytearray()
    for point in sound:
        if type(point) is tuple:
            left, right = point
        else:
            left = right = point
        left = max(low, min(high, int(volume * left)))
        right = max(low, min(high, int(volume * right)))
        current += int_to_bytes(left, 2, "little", signed=True)
        current += int_to_bytes(right, 2, "little", signed=True)
        if len(current) >= size:
            yield bytes(current)
            current.clear()
    if current:
        while not len(current) >= size:
            current += b"\x00\x00\x00\x00"
        yield bytes(current)
chunk = chunked  # Old name

def unwrap_discord_source(source, /):
    """Converts an audio source into a stream of bytes

    This basically does the opposite of wrap_discord_source. See that function's
    documentation for more info.

    """
    try:
        while chunk := source.read():
            yield chunk
    finally:
        try:
            cleanup = source.cleanup
        except AttributeError:
            pass
        else:
            cleanup()
source_to_iterator = unwrap_discord_source  # Old name

def unchunked(chunks, /):
    """Converts a stream of bytes to two-tuples of floats in [-1, 1)

    This basically does the opposite of chunked. See that function's
    documentation for more info.

    """
    volume = 1 << (16-1)  # 16-bit signed
    int_from_bytes = int.from_bytes  # speedup by removing a getattr
    for chunk in chunks:
        for i in range(0, len(chunk) - len(chunk)%4, 4):
            left = int_from_bytes(chunk[i:i+2], "little", signed=True)
            right = int_from_bytes(chunk[i+2:i+4], "little", signed=True)
            yield left/volume, right/volume
unchunk = unchunked  # Old name

# - Utility for note names and the like

def make_frequencies_dict(*, a4=A4_FREQUENCY, offset=0):
    """Makes a dictionary containing frequencies for each note

     - a4 is the frequency for the A above middle C
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
    """Makes a dictionary containing note indices of common note names

     - a4 is the note index for the A above middle C
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
    # Process lines
    processed = []
    for line in music.splitlines():
        # Skip empty lines and comments
        line = line.strip()
        if line == "":
            continue
        if line.startswith("#"):
            continue

        # Split into notes
        parts = line.split()
        for part in parts:
            part_length = line_length / len(parts)
            notes = part.split(",")
            for note in notes:
                note_length = part_length / len(notes)

                # Get flags and add to notes list
                flags = ""
                if note.endswith("~"):
                    note = note.removesuffix("~")
                    flags += "~"
                elif note.endswith("!"):
                    note = note.removesuffix("!")
                    flags += "!"
                processed.append((note, flags, note_length))

    # Generate notes
    notes = []
    last_note = "."
    for i, (note, flags, note_length) in enumerate(processed):
        has_silence = True

        # Check flags for silence
        if i+1 < len(processed) and processed[i+1][0] == "-":
            has_silence = False
        if "~" in flags:
            has_silence = False
        if "!" in flags:
            has_silence = True

        # Get last note if current is a "-"
        if note == "-":
            note = last_note

        # Get length of silence
        silent_length = 0
        if has_silence:
            silent_length = min(0.1, 0.25*note_length)
            note_length -= silent_length
        if note == ".":
            silent_length += note_length
            note_length = 0

        # Get / update note lengths
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
    import importlib
    name = __name__.partition(".")[0]
    importlib.reload(importlib.import_module(name))


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

# Use split_music to separate top and bottom parts
MUSIC_DIGITIZED_DUAL = '''
    # names="do di re ri mi fa fi so si la li ti".split()
    # line_length=4.36
    # offset=13
/   # offset=1

    . mi mi mi fa       do . do .           so mi do re         mi,re - mi
/   .

    la3 mi mi mi        fa do . do          . so mi do          re mi,re - mi
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do mi mi mi         fa do . do          . so mi do          re mi,re - mi
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do mi mi mi         fa do . do          . so mi do          re mi,re - mi
/   la3 la3 la3 la3     la3 la3 la3 la3     la3 la3 la3 la3     la3 la3 la3 la3

    do mi mi mi         fa do . do          . so mi do          . . . .
/   la3 la3 la3 la3     la3 la3 la3 la3     la3 la3 la3 la3     la3,do,mi,so la,do5,mi5,so5 la5 .

    do so mi do         re re,mi so mi      do so mi do         re re,mi so re
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do so mi do         re re,mi so mi      do so mi do         re re,mi so re
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    - do . la3          . la3 do re         so3 do mi do        re do,re - do
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    - do . la3          . la3 do re         so3 do mi do        re do,re - do
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do la3 - so3        do re,mi - re       . . do so3          re mi re do
/   .

    . . do so3          fa mi,re - do       - so3 re do         mi so re do
/   .

    la3 mi mi mi        fa do . do          . so mi do          re mi,re - mi
/   la3 . la3 .         fa3 . fa3 .         do . do .           so3 . so3 .

    do mi mi mi         fa do . do          . so mi do          re mi,re - mi
/   la3 . la3 .         fa3 . fa3 .         do . do .           so3 . so3 .

    do mi mi mi         fa do . do          . so mi do          re mi,re - mi
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do mi mi mi         fa do . do          . so mi do          . . . .
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        la3,do,mi,so la,do5,mi5,so5 la5 .

    do so mi do         re re,mi so mi      do so mi do         re re,mi so re
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do so mi do         re re,mi so mi      do so mi do         re re,mi so re
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    - do . la3          . la3 do re         so3 do mi do        re do,re - do
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    - do . la3          . la3 do re         so3 do mi do        re do,re - -
/   la3 la3 la3 fa3     fa3 fa3 fa3 fa3     do do do so3        so3 so3 si3 si3

    do . . .
/   la3 . . .
'''
