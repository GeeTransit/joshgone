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
    chunk
    unchunk

discord.py utilities:
    iterator_to_source
    source_to_iterator

FFmpeg utilities:
    process_from_ffmpeg_args
    iterator_from_process

A very simple example: (Note that ctx is a discord.Context)

    import sound as s
    await s.play_source(
        ctx.voice_client,
        s.iterator_to_source(s.chunk(s.sine(440, seconds=1))),
    )

A longer example:

    import itertools
    import sound as s

    indices = s.make_indices_dict()
    frequencies = s.make_frequencies_dict()
    notes = "a3 c e a g e c e d e d c a3 c a3 g3".split()

    await s.play_source(
        ctx.voice_client,
        s.iterator_to_source(s.chunk(itertools.chain.from_iterable(
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

    await s.play_source(
        ctx.voice_client,
        s.iterator_to_source(s.chunk(
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
import json
import itertools
import functools
import subprocess

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
    """Returns 0 for the specified amount of time"""
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
    the form `https://onlinesequencer.net/app/instruments/{i}.ogg?v=12` with
    `{i}` being replaced with the instrument number. The settings are from
    `https://onlinesequencer.net/resources/c/85dda66875c37703d44f50da0bb85185.js`.

    The raw audio files were generated using FFmpeg using a command of the form
    `ffmpeg -i {i}.ogg -f s16le -acodec pcm_s16le -ac 1 -ar 48000 {i}.raw` with
    `{i}` being replaced with the instrument number. The raw files are 48 kHz
    signed 16-bit little endian mono audio.

    Online Sequencer's lowest note index (0) represents a C2, which would be 24
    according to make_indices_dict. All note indices are offset accordingly.

    """
    _SETTINGS_FILENAME = "onlinesequencer_settings.json"
    _INSTRUMENT_FILENAME = "./_ossounds/{i}.raw"
    _INDEX_OFFSET = 2 * 12

    _settings = None
    _data = {}

    def __init__(self, instrument):
        """Creates an instrument

        If the instrument is a string, it is looked up and converted into an
        instrument number.

        """
        # Load settings and data
        self.load_settings()
        if type(instrument) is str:
            instrument = self._settings["instruments"].index(instrument)
        self.load_data(instrument)
        # Store them on the instrument
        self.instrument = instrument
        self.instrument_name = self._settings["instruments"][instrument]
        self.data = self._data[instrument]
        self.min = self._settings["min"][instrument] + self._INDEX_OFFSET
        self.max = self._settings["max"][instrument] + self._INDEX_OFFSET
        self.original_bpm = self._settings["originalBpm"][instrument] * 2
        self.seconds = 60 / self.original_bpm

    def at(self, index=A4_INDEX):
        """Returns a sound for this instrument at the specified note index"""
        if not self.min <= index <= self.max:
            return
        RATE = 48000  # 48 kHz
        HIGHEST = 1 << 16-1  # signed 16 bit little endian
        start = (index - self.min) * self.seconds
        for x in passed(self.seconds):
            i = int((start + x) * RATE + 0.5) * 2
            yield int.from_bytes(
                self.data[i:i+2],
                "little",
                signed=True,
            ) / HIGHEST

    @classmethod
    def load_settings(cls, *, force=False):
        if not force and cls._settings is not None:
            return False
        with open(cls._SETTINGS_FILENAME) as file:
            cls._settings = json.load(file)
        return True

    @classmethod
    def load_data(cls, instrument, *, force=False):
        assert type(instrument) is int
        if not force and cls._data.get(instrument, None) is not None:
            return False
        filename = cls._INSTRUMENT_FILENAME.replace("{i}", str(instrument))
        with open(filename, mode="rb") as file:
            cls._data[instrument] = file.read()
        return True

# - LRU cache for iterators

class LRUIterableCache:
    """An LRU cache for iterables

    The maxsize argument specifies the maximum size the cache can grow to.
    Specifying 0 means that the cache will remain empty. Specifying None means
    the cache will grow without bound.

    To get an iterable, call .get with a key (to uniquely identify each
    iterable, and with a zero-argument function that returns an iterable for
    when it doesn't exist.

    The resulting iterator can be iterated upon normally. The values returned
    are stored for future calls. They can also be consumed at different speeds.

    To clear the cache and reset the hits / misses counters, call .clear().

    To change the maxsize, set the .maxsize property to its new value. Note
    that it won't take effect until the next .get call with a key not in the
    cache. It is not recommended, but you can call ._ensure_size() to force
    it to resize the cache.

    For info on the number of hits / misses, check the .hits and .misses
    attributes. You can reset them to 0 manually if you'd like.

    Checking and modifying the cache manually isn't recommended, but they are
    available through the .iterators and .results attributes. The former stores
    ongoing iterators (ones that haven't ended) and the latter holds a list of
    the yielded values. You can clear them manually if you'd like.

    """
    def __init__(self, *, maxsize=128):
        # Set cache state
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0
        self.iterators = {}  # Stores the running iterator
        self.results = {}  # Stores the list of yielded values

    def get(self, key, iterable_func):
        """Return an iterator for this key, calling iterable_func if needed"""
        # If the key ain't in the cache...
        if key not in self.results:
            # Get the iterator from calling the function
            iterator = iter(iterable_func())
            # Update cache with the iterator
            self._miss(key, iterator)
            # Ensure the cache's size isn't over self.maxsize
            self._ensure_size()
            # If the keys we just removed was ours...
            if key not in self.iterators:
                # Yield from the iterator directly (not in the cache)
                return iter(iterator)

        # If the key is in the cache...
        else:
            result = self._hit(key)
            # If there is no ongoing iterator...
            if key not in self.iterators:
                # Yield from the result directly (iterator already ended)
                return iter(result)

        # The iterator is in the cache and it's still being stepped through.
        return self._wrap_iterator(key)

    def clear(self):
        """Clears the cache"""
        self.results.clear()
        self.iterators.clear()

    def __repr__(self):
        maxsize = self.maxsize
        hits = self.hits
        misses = self.misses
        return f"<{type(self).__name__} {maxsize=} {hits=} {misses=}>"

    def _miss(self, key, iterator):
        # Note down that we missed it
        self.misses += 1
        # Update cache with the iterator
        self.iterators[key] = iterator
        self.results[key] = []
        return iterator

    def _hit(self, key):
        # Note down that we hit it
        self.hits += 1
        # Move key to the end of the dict (LRU cache)
        result = self.results.pop(key)
        self.results[key] = result
        return result

    def _ensure_size(self):
        if self.maxsize is None:  # Cache is not unbounded
            return False
        if len(self.results) <= max(0, self.maxsize):
            return False
        # Fast path for maxsize of 0 (clear everything)
        if self.maxsize == 0:
            self.results.clear()
            self.iterators.clear()
            return True
        # Get old keys in the cache (order is kept in a dict)
        old_keys = list(itertools.islice(
            iter(self.results.keys()),
            len(self.results) - self.maxsize,
        ))
        # Remove old keys
        for old_key in old_keys:
            self.results.pop(old_key)
            self.iterators.pop(old_key, None)
        # Force a resizing of the dictionaries (resize on inserts)
        self.results[1] = 1
        del self.results[1]
        self.iterators[1] = 1
        del self.iterators[1]
        return True

    def _wrap_iterator(self, key):
        iterator = self.iterators[key]
        result = self.results[key]
        # Use itertools.count because we don't know how long the iterator is.
        for index in itertools.count():
            # If the next value hasn't been added yet...
            if not index < len(result):
                assert index == len(result)  # Quick sanity check on the index
                try:
                    # Try getting the next value
                    value = next(iterator)
                except StopIteration:
                    # The iterator has ended. Remove it from the iterator dict.
                    # Note that this depends on the fact that calling
                    # next(iterator) after an iterator has ended always raises
                    # StopIteration.
                    self.iterators.pop(key, None)
                    break
                else:
                    # Update the cache with the new value
                    result.append(value)
            # Yield the next value
            yield result[index]

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

def process_from_ffmpeg_args(
    *args,
    executable="ffmpeg",
    pipe_stdin=False,
    pipe_stdout=True,
    pipe_stderr=False,
    **kwargs,
):
    """Creates a process that run FFmpeg with the given arguments

    This assumes that ffmpeg.exe is on your PATH environment variable. If not,
    you can specify the executable argument to the executable's location.

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

def iterator_from_process(process):
    """Returns an iterator of chunks from the given process

    This function is hardcoded to take PCM 16-bit stereo audio.

    """
    SAMPLING_RATE = 48000  # 48kHz
    CHANNELS = 2  # stereo
    SAMPLE_WIDTH = 2 * 8  # 16-bit
    FRAME_LENGTH = 20  # 20ms

    SAMPLE_SIZE = SAMPLE_WIDTH * CHANNELS
    SAMPLES_PER_FRAME = round(SAMPLING_RATE * FRAME_LENGTH / 1000)
    FRAME_SIZE = SAMPLES_PER_FRAME * SAMPLE_SIZE

    try:
        read = process.stdout.read
        while data := read(FRAME_SIZE):
            yield data

    finally:
        process.kill()
        if process.poll() is None:
            process.communicate()

# - Experimental OS instrument with no FFmpeg preprocessing

class _OSInstrumentFFmpeg:
    """An instrument wrapping a collection of sounds

    These sounds are taken from Online Sequencer. More info can be found in
    the _OSInstrument class.

    Note that no FFmpeg preprocessing is needed; all reencoding is done at
    runtime. However, you can still specify a raw PCM file. Just also pass
    the relevant FFmpeg options specifying the format, sample rate, and number
    of channels. For 48 kHz signed 16-bit little endian mono audio, you'd pass
    `before_options="-f s16le -ar 48000 -ac 1"`.

    """
    _SETTINGS_FILENAME = "onlinesequencer_settings.json"
    _INSTRUMENT_FILENAME = "./_ossounds/<>.ogg"
    _INDEX_OFFSET = 2 * 12

    _settings = None

    def __init__(
        self,
        instrument,
        * ,
        filename=None,
        before_options=None,
        options=None,
    ):
        """Create an instrument

        The filename can optionally have a pair of angle brackets `<>` which
        will be replaced by the instrument number.

        The before_options and options arguments are included in the
        .ffmpeg_args_for method's return value. Note that they will be prefixed
        by `["-ss", str(start_time)]` for before_options and
        `["-t", str(self.seconds)]` for options.

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
        # FFmpeg options
        self.filename = filename
        self.before_options = before_options
        self.options = options

    def at(self, index=A4_INDEX):
        """Returns a sound for this instrument at the specified note index"""
        # Get the starting time of this note
        start = self.start_of(index)
        # If the index is out of range, return an empty sound (no points)
        if start is None:
            return
        # Get FFmpeg arguments
        args = self.ffmpeg_args_for(start)
        # Create the process
        process = process_from_ffmpeg_args(*args)
        # Create an iterator from the process
        iterator = iterator_from_process(process)
        # Unchunk and convert into a sound
        yield from ((x+y)/2 for x, y in unchunk(iterator))

    def start_of(self, index=A4_INDEX):
        """Returns the start time for the specified note"""
        # If the index is out of range, return None
        if not self.min <= index <= self.max:
            return None
        # Return the starting place otherwise
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

# - Cached OS instrument with no FFmpeg preprocessing

class _OSInstrumentFFmpegCached(_OSInstrumentFFmpeg):
    """An instrument wrapping a cached collection of sounds

    Note that we cache the binary data, not the floats, as this reduces
    memory usage by a lot (at the cost of some more CPU usage).

    See _OSInstrumentFFmpeg for more info.

    """
    def __init__(self, instrument, * , max_cache_size=128, **kwargs):
        """Creates an instrument with the specified cache size

        See _OSInstrumentFFmpeg.__init__ for more info on the instrument and
        other keyword arguments.

        See LRUIterableCache for more info on max_cache_size and on caching.

        """
        super().__init__(instrument, **kwargs)
        # Create the cache for source iterators
        self.cache = LRUIterableCache(maxsize=max_cache_size)

    def at(self, index=A4_INDEX):
        """Returns a sound at the specified note index

        Note that the source iterable may be cached. Thus, if the file changes,
        the returned sounds may not be updated. Use .cache_clear() to refresh
        the cache.

        """
        # If the index is out of range, return an empty sound (no points)
        start = self.start_of(index)
        if start is None:
            return ()
        # Check the cache before getting the sound
        iterator = self.cache.get(index, lambda: self._iterator_at(start))
        # Unchunk and convert into a sound
        yield from ((x+y)/2 for x, y in unchunk(iterator))

    def _iterator_at(self, start):
        # Get FFmpeg arguments
        args = self.ffmpeg_args_for(start)
        # Create the process
        process = process_from_ffmpeg_args(*args)
        # Create an iterator from the process
        return iterator_from_process(process)

    def cache_clear(self):
        """Clears the source iterables cache

        Same as doing .cache.clear().

        """
        self.cache.clear()

# - Experimental OS sound functions

_onlinesequencer_data = {}
_onlinesequencer_settings = None

def _init_onlinesequencer_sound(instrument):
    assert type(instrument) is int
    if instrument in _onlinesequencer_data:
        return
    with open(f"{instrument}.raw", mode="rb") as file:
        _onlinesequencer_data[instrument] = file.read()

def _init_onlinesequencer_settings():
    global _onlinesequencer_settings
    if _onlinesequencer_settings is not None:
        return
    with open("onlinesequencer_settings.json") as file:
        _onlinesequencer_settings = json.load(file)

def _onlinesequencer_sound(instrument, index=A4_INDEX):
    index -= 2*12  # All instruments start at C2
    seconds_per_beat = 60 / (_onlinesequencer_settings["originalBpm"][instrument] * 2)
    data = _onlinesequencer_data[instrument]
    min_ = _onlinesequencer_settings["min"][instrument]
    max_ = _onlinesequencer_settings["max"][instrument]
    if not min_ <= index <= max_:
        return
    index -= min_
    for i in range(int(index*seconds_per_beat * RATE)*2, int((index+1)*seconds_per_beat * RATE)*2, 2):
        yield int.from_bytes(data[i:i+2], "little", signed=True) / (1<<16-1)


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

if has_discord:
    # Make our class a subclass of discord.py AudioSource if possible
    class IteratorSource(discord.AudioSource):
        """Internal subclass of discord's AudioSource for iterators

        See iterator_to_source for more info.

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

def iterator_to_source(iterator, /, *, is_opus=False):
    """Wraps an iterator of bytes into an audio source

    If is_opus is False (the default), the iterator must yield 20ms of signed
    16-bit little endian stereo 48kHz audio each iteration. If is_opus is True,
    the iterator should yield 20ms of Opus encoded audio each iteration.

    Usage:
        # returns an audio source implementing AudioSource
        source = s.iterator_to_source(s.chunk(s.sine(440, seconds=1)))
        ctx.voice_client.play(source, after=lambda _: print("finished"))

    """
    if not has_discord:
        raise RuntimeError("discord.py needed to make discord.AudioSources")
    return IteratorSource(iterator, is_opus=is_opus)

def chunk(iterator, /):
    """Converts a stream of floats or two-tuples of floats in [-1, 1) to bytes

    This is hardcoded to return 20ms chunks of signed 16-bit little endian
    stereo 48kHz audio.

    If the iterator returns a single float, it will have both sides play the
    same point.

    If the iterator doesn't complete on a chunk border, null bytes will be
    added until it reaches the required length, which should be 3840 bytes.

    Note that floats not in the range [-1, 1) will be silently truncated to
    fall inside the range.

    """
    volume = 1 << (16-1)  # 16-bit signed
    high, low = volume-1, -volume  # allowed range
    rate = 48000  # 48kHz
    chunks_per_second = 1000//20  # 20ms
    points_per_chunk = rate//chunks_per_second
    size = points_per_chunk * 2 * 2  # 16-bit stereo
    int_to_bytes = int.to_bytes  # speedup by removing a getattr
    current = bytearray()
    for num in iterator:
        if type(num) is tuple:
            left, right = num
        else:
            left = right = num
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

def source_to_iterator(source, /):
    """Converts an audio source into a stream of bytes

    This basically does the opposite of iterator_to_source. See that function's
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

def unchunk(chunks, /):
    """Converts a stream of bytes to two-tuples of floats in [-1, 1)

    This basically does the opposite of chunk. See that function's
    documentation for more info.

    """
    volume = 1 << (16-1)  # 16-bit signed
    int_from_bytes = int.from_bytes  # speedup by removing a getattr
    for chunk in chunks:
        for i in range(0, len(chunk) - len(chunk)%4, 4):
            left = int_from_bytes(chunk[i:i+2], "little", signed=True)
            right = int_from_bytes(chunk[i+2:i+4], "little", signed=True)
            yield left/volume, right/volume

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
