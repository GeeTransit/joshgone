# Source: https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py

import asyncio
import random
import typing
import traceback
import json
import queue
import threading
import os
import sys
import shlex
from collections import deque

import discord
from discord.ext import commands
from discord.ext import tasks

import yt_dlp as youtube_dl

import patched_player
import soundit as s

try:
    import online_sequencer_get_note_infos as os_note_infos
except ImportError:
    has_os = False
else:
    has_os = True

class Music(commands.Cog):
    # Options that are passed to youtube-dl
    _DEFAULT_YTDL_OPTS = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'playlistend': 1,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0', # bind to ipv4 since ipv6 addresses cause issues sometimes
    }
    # Options passed to FFmpeg
    _DEFAULT_FFMPEG_OPTS = {
        'options': '-vn',
        # Source: https://stackoverflow.com/questions/66070749/
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    }

    ONLINE_SEQUENCER_URL_PREFIX = "https://onlinesequencer.net/"

    def __init__(
        self,
        bot,
        *,
        ytdl_opts=_DEFAULT_YTDL_OPTS,
        ffmpeg_opts=_DEFAULT_FFMPEG_OPTS,
        os_python_executable=None,
        os_directory=None,
    ):
        self.bot = bot
        # Options are stores on the instance in case they need to be changed
        self.ytdl_opts = ytdl_opts
        self.ffmpeg_opts = ffmpeg_opts
        # Data is persistent between extension reloads
        if not hasattr(bot, "_music_data"):
            bot._music_data = {}
        if not hasattr(bot, "_music_advance_queue"):
            bot._music_advance_queue = asyncio.Queue()
        self.data = bot._music_data
        self.advance_queue = bot._music_advance_queue
        # Start the advancer's auto-restart task
        self.advance_task = None
        self.advancer.start()
        # The name of the Python executable we should use for Online Sequencer
        if os_python_executable is None:
            os_python_executable = os.environ.get(
                "JOSHGONE_OS_PY_EXE",
                sys.executable,  # We default to using the current Python
            )
        self.os_python_executable = os_python_executable
        # The directory with the Online Sequencer instrument settings and audio
        if os_directory is None:
            os_directory = os.environ.get(
                "JOSHGONE_OS_DIRECTORY",
                "oscollection",
            )
        self.os_directory = os_directory

    # Cancel just the advancer and the auto-restart tasks
    def cog_unload(self):
        self.advancer.cancel()

    # - Song players
    # Returns a source object and the title of the song

    # Finds a file using query. Title is query
    async def _play_local(self, query):
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        return source, query

    # Searches various sites using url. Title is data["title"] or url
    async def _play_stream(self, url):
        original_url = url
        if url[0] == "<" and url[-1] == ">":
            url = url[1:-1]
        player, data = await self.player_from_url(url, stream=True)
        return player, data.get("title", original_url)

    # Converts an Online Sequencer sequence into a sound. Title is url
    async def _play_os(self, url):
        original_url = url
        if url[0] == "<" and url[-1] == ">":
            url = url[1:-1]
        source = await self._create_os_source(url)
        return source, original_url

    # Returns the raw source (calling the function if possible)
    async def _play_raw(self, source):
        if callable(source):
            source = source()
        if not isinstance(source, discord.AudioSource):
            source = s.wrap_discord_source(s.chunked(source))
        return source, repr(source)

    # Auto-restart task for the advancer task
    @tasks.loop(seconds=15)
    async def advancer(self):
        if self.advance_task is not None and self.advance_task.done():
            try:
                exc = self.advance_task.exception()
            except asyncio.CancelledError:
                pass
            else:
                print("Exception occured in advancer task:")
                traceback.print_exception(None, exc, exc.__traceback__)
            self.advance_task = None
        if self.advance_task is None:
            self.advance_task = asyncio.create_task(self.handle_advances(), name="music_advancer")

    # Cancel the advancer task if the monitoring task is getting cancelled
    # (such as when the cog is getting unloaded)
    @advancer.after_loop
    async def on_advancer_cancel(self):
        if self.advancer.is_being_cancelled():
            if self.advance_task is not None:
                self.advance_task.cancel()
                self.advance_task = None

    # The advancer task loop
    async def handle_advances(self):
        while True:
            item = await self.advance_queue.get()
            asyncio.create_task(self.handle_advance(item))

    # The actual music advancing logic
    async def handle_advance(self, item):
        ctx, error = item
        info = self.get_info(ctx)
        channel = ctx.guild.get_channel(info["channel_id"])
        try:
            # If we are processing it right now...
            if info["processing"]:
                # Wait a bit and reschedule it again
                await asyncio.sleep(1)
                self.advance_queue.put_nowait(item)
                return
            info["processing"] = True
            # If there's an error, send it to the channel
            if error is not None:
                await channel.send(f"Player error: {error!r}")
            # If we aren't connected anymore, notify and leave
            if ctx.voice_client is None:
                await channel.send("Not connected to a voice channel anymore")
                await self.leave(ctx)
                return
            queue = info["queue"]
            # If we're looping, put the current song at the end of the queue
            if info["loop"] and info["current"] is not None:
                queue.append(info["current"])
            info["current"] = None
            if queue:
                # Get the next song
                current = queue.popleft()
                info["current"] = current
                # Get an audio source and play it
                after = lambda error, ctx=ctx: self.schedule(ctx, error)
                async with channel.typing():
                    source, title = await getattr(self, f"_play_{current['ty']}")(current['query'])
                    ctx.voice_client.play(source, after=after)
                await channel.send(f"Now playing: {title}")
            else:
                await channel.send(f"Queue empty")
        except Exception as e:
            await channel.send(f"Internal Error: {e!r}")
            info["waiting"] = False
            await self.skip(ctx)
            self.schedule(ctx)
        finally:
            info["waiting"] = False
            info["processing"] = False

    # Schedules advancement of the queue
    def schedule(self, ctx, error=None, *, force=False):
        info = self.get_info(ctx)
        if force or not info["waiting"]:
            self.advance_queue.put_nowait((ctx, error))
            info["waiting"] = True

    # Helper function to create the info for a guild
    def get_info(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.data:
            wrapped = self.data[guild_id] = {}
            wrapped["queue"] = deque()
            wrapped["current"] = None
            wrapped["waiting"] = False
            wrapped["loop"] = False
            wrapped["processing"] = False
            wrapped["version"] = 3
        else:
            wrapped = self.data[guild_id]
        if wrapped["version"] == 3:
            wrapped["channel_id"] = ctx.channel.id
            wrapped["version"] = 4
        return wrapped

    # Helper function to remove the info for a guild
    def pop_info(self, ctx):
        return self.data.pop(ctx.guild.id, None)

    # Creates an audio source from a url
    async def player_from_url(self, url, *, loop=None, stream=False):
        ytdl = youtube_dl.YoutubeDL(self.ytdl_opts)
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        audio = patched_player.FFmpegPCMAudio(filename, **self.ffmpeg_opts)
        player = discord.PCMVolumeTransformer(audio)
        return player, data

    # Creates an audio source from an Online Sequencer url
    async def _create_os_source(self, url):
        # Verify that the url is valid
        if url.startswith(self.ONLINE_SEQUENCER_URL_PREFIX):
            id_ = int(url[len(self.ONLINE_SEQUENCER_URL_PREFIX):])
        else:
            id_ = int(url)
        # Create the url and get note infos
        url = f"{self.ONLINE_SEQUENCER_URL_PREFIX}{id_}"
        note_infos = await os_note_infos.get_note_infos(url)
        # Start another process to convert these into a sound
        executable, *args = shlex.split(self.os_python_executable)
        process = await asyncio.to_thread(
            lambda: s.create_ffmpeg_process(
                *args,
                "online_sequencer_make_chunks.py",
                "--settings", f"{self.os_directory}/settings.json",
                "--template", f"{self.os_directory}/<>.ogg",
                executable=executable,
                pipe_stdin=True,
                pipe_stdout=True,
            )
        )
        # Start a background task to send in note infos through stdin
        asyncio.create_task(asyncio.to_thread(
            lambda: (
                process.stdin.write(json.dumps(note_infos).encode()),
                process.stdin.close(),
            )
        ))
        # Make a small buffer to make audio more consistent
        chunks_queue = queue.Queue(maxsize=64)
        stop = False  # Flag for producer to stop
        producer_event = threading.Event()  # Notifies producer to continue
        # The sound producer / loader (moves sound from process to the queue)
        def producer():
            try:
                # Loop over chunks of the process's stdout
                for chunk in s.equal_chunk_stream(
                    s.chunked_ffmpeg_process(process),
                    3840,
                ):
                    chunk = bytes(chunk)
                    while True:
                        # Check if we need to stop
                        if stop:
                            return
                        # Clear the event before we try getting an item just in
                        # case of bad timing (event gets cleared just after we
                        # try putting an item).
                        producer_event.clear()
                        try:
                            # Try putting the chunk
                            chunks_queue.put(chunk, block=False)
                        except queue.Full:
                            # Wait for the event to be set
                            cleared = producer_event.wait(timeout=5)
                            # If the event isn't set after 5 seconds...
                            if not cleared:
                                # Assume our audio player is too slow and error
                                raise RuntimeError("Sound player too slow")
                        else:
                            # If all went well, go process the next chunk
                            break
            except BaseException as e:
                # Let the consumer know we errored
                chunks_queue.put(e, timeout=5)
            finally:
                # Let the consumer know we ended
                chunks_queue.put(None, timeout=5)
        # Make a thread for the producer
        task = asyncio.create_task(asyncio.to_thread(lambda: producer()))
        # Ignore exceptions (kinda like a daemon task)
        task.add_done_callback(lambda task: task.exception())
        # The sound consumer / player (yields from queue to the audio source)
        def consumer():
            try:
                # Loop until we have no more chunks to process
                while True:
                    try:
                        # Try getting an item
                        item = chunks_queue.get(timeout=5)
                    except queue.Empty:
                        # If we needed to wait more than 5 seconds, assume the
                        # loader is too slow and tell it to stop
                        raise RuntimeError("Sound loader too slow")
                    else:
                        # Tell the producer it can put more items
                        producer_event.set()
                    # If the producer has ended, we should end too
                    if item is None:
                        return
                    # If the producer errored, reraise it here
                    if isinstance(item, BaseException):
                        raise item
                    # Otherwise, it's just a normal chunk of audio. Yield it
                    yield item
            finally:
                # Tell the producer to stop if it's still running
                nonlocal stop
                stop = True
                producer_event.set()
                # Terminate the process
                process.stdout.close()
                process.stdin.close()
                process.terminate()
                process.wait()
        # Wrap the sound player chunk iterator with an audio source
        source = s.wrap_discord_source(consumer())
        # Wait a lil bit to get the chunk queue prefilled
        await asyncio.sleep(2)
        # Return the audio source
        return source

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel

        Text output will be sent from the channel this command was run in. This
        command can be run multiple times safely.

        """
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        info = self.get_info(ctx)
        if info["channel_id"] != ctx.channel.id:
            info["channel_id"] = ctx.channel.id
            await ctx.send("Switching music output to this channel")

    @commands.command()
    @commands.is_owner()
    async def local(self, ctx, *, query):
        """Plays a file from the local filesystem"""
        info = self.get_info(ctx)
        queue = info["queue"]
        queue.append({"ty": "local", "query": query})
        if info["current"] is None:
            self.schedule(ctx)
        await ctx.send(f"Added to queue: local {query}")

    @commands.command(aliases=["yt", "play", "p"])
    async def stream(self, ctx, *, url):
        """Plays from a url (almost anything youtube_dl supports)"""
        if len(url) > 100:
            raise ValueError("url too long (length over 100)")
        if not url.isprintable():
            raise ValueError(f"url not printable: {url!r}")
        print(ctx.message.author.name, "queued", repr(url))
        info = self.get_info(ctx)
        queue = info["queue"]
        ty = "local" if url == "coco.mp4" else "stream"
        queue.append({"ty": ty, "query": url})
        if info["current"] is None:
            self.schedule(ctx)
        await ctx.send(f"Added to queue: {ty} {url}")

    if has_os:
        @commands.command(name="_play_os")
        async def play_os(self, ctx, *, url):
            """Plays an Online Sequencer sequence"""
            if len(url) > 100:
                raise ValueError("url too long (length over 100)")
            if not url.isprintable():
                raise ValueError(f"url not printable: {url!r}")
            print(ctx.message.author.name, "queued", repr(url))
            info = self.get_info(ctx)
            queue = info["queue"]
            queue.append({"ty": "os", "query": url})
            if info["current"] is None:
                self.schedule(ctx)
            await ctx.send(f"Added to queue: os {url}")

    async def add_to_queue(self, ctx, source):
        """Plays the specified source"""
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                raise RuntimeError("Author not connected to a voice channel")
        info = self.get_info(ctx)
        queue = info["queue"]
        queue.append({"ty": "raw", "query": source})
        if info["current"] is None:
            self.schedule(ctx)

    @commands.command()
    async def _add_playlist(self, ctx, *, url):
        """Adds all songs in a playlist to the queue"""
        if len(url) > 100:
            raise ValueError("url too long (length over 100)")
        if not url.isprintable():
            raise ValueError(f"url not printable: {url!r}")
        print(ctx.message.author.name, "queued playlist", repr(url))
        bracketed = False
        if url[0] == "<" and url[-1] == ">":
            bracketed = True
            url = url[1:-1]
        info = self.get_info(ctx)
        queue = info["queue"]
        ytdl = youtube_dl.YoutubeDL(self.ytdl_opts | {
            'noplaylist': None,
            'playlistend': None,
            "extract_flat": True,
        })
        data = await asyncio.to_thread(ytdl.extract_info, url, download=False)
        if 'entries' not in data:
            raise ValueError("cannot find entries of playlist")
        entries = data['entries']
        for entry in entries:
            url = f"https://www.youtube.com/watch?v={entry['url']}"
            if bracketed:
                url = f"<{url}>"
            queue.append({"ty": "stream", "query": url})
        if info["current"] is None:
            self.schedule(ctx)
        await ctx.send(f"Added playlist to queue: {url}")

    @commands.command(name="batch_add")
    async def _batch_add(self, ctx, *, urls):
        """Plays from multiple urls split by lines"""
        for url in urls.splitlines():
            await self.stream(ctx, url=url)
            await asyncio.sleep(0.1)

    @commands.command()
    async def shuffle(self, ctx):
        """Shuffles the queue"""
        info = self.get_info(ctx)
        queue = info["queue"]
        temp = []
        while queue:
            temp.append(queue.popleft())
        random.shuffle(temp)
        while temp:
            queue.appendleft(temp.pop())
        await ctx.send("Queue shuffled")

    @commands.command()
    async def volume(self, ctx, volume: float = None):
        """Gets or changes the player's volume"""
        if volume is None:
            volume = ctx.voice_client.source.volume * 100
            if int(volume) == volume:
                volume = int(volume)
            await ctx.send(f"Volume set to {volume}%")
            return
        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel")
        try:
            if int(volume) == volume:
                volume = int(volume)
        except (OverflowError, ValueError):
            pass
        if not await self.bot.is_owner(ctx.author):
            # prevent insane ppl from doing this
            volume = min(100, volume)
        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"Changed volume to {volume}%")

    @commands.command(aliases=["stop"])
    async def pause(self, ctx):
        """Pauses playing"""
        ctx.voice_client.pause()

    @commands.command(aliases=["start"])
    async def resume(self, ctx):
        """Resumes playing"""
        ctx.voice_client.resume()

    @commands.command()
    async def leave(self, ctx):
        """Disconnects the bot from voice and clears the queue"""
        self.pop_info(ctx)
        if ctx.voice_client is None:
            return
        await ctx.voice_client.disconnect()

    @commands.command(aliases=["c"])
    async def current(self, ctx):
        """Shows the current song"""
        query = None
        if ctx.voice_client is not None:
            info = self.get_info(ctx)
            current = info["current"]
            if current is not None and not info["waiting"]:
                query = current["query"]
        await ctx.send(f"Current: {query}")

    @commands.command(aliases=["q"])
    async def queue(self, ctx):
        """Shows the songs on queue"""
        queue = ()
        length = 0
        looping = False
        if ctx.voice_client is not None:
            info = self.get_info(ctx)
            queue = info["queue"]
            length = len(queue)
            looping = info["loop"]
        if not queue:
            queue = (None,)
        paginator = commands.Paginator()
        paginator.add_line(f"Queue [{length}]{' (looping)'*looping}:")
        for i, song in enumerate(queue, start=1):
            if song is None:
                paginator.add_line("None")
            else:
                paginator.add_line(f"{i}: {song['query']}")
        for page in paginator.pages:
            await ctx.send(page)

    def normalize_index(self, ctx, position, length):
        index = position
        if index > 0:
            index -= 1
        if index < 0:
            index += length
        if not 0 <= index < length:
            raise ValueError(position)
        return index

    @commands.command()
    async def remove(self, ctx, position: int):
        """Removes a song on queue"""
        info = self.get_info(ctx)
        queue = info["queue"]
        try:
            index = self.normalize_index(ctx, position, len(queue))
        except ValueError:
            raise commands.CommandError(f"Index out of range [{position}]")
        queue.rotate(-index)
        song = queue.popleft()
        queue.rotate(index)
        await ctx.send(f"Removed song [{position}]: {song['query']}")

    @commands.command()
    async def move(self, ctx, origin: int, target: int):
        """Moves a song on queue"""
        info = self.get_info(ctx)
        queue = info["queue"]
        try:
            origin_index = self.normalize_index(ctx, origin, len(queue))
        except ValueError:
            raise commands.CommandError(f"Origin index out of range [{origin}]")
        try:
            target_index = self.normalize_index(ctx, target, len(queue))
        except ValueError:
            raise commands.CommandError(f"Target index out of range [{target}]")
        queue.rotate(-origin_index)
        song = queue.popleft()
        queue.rotate(origin_index - target_index)
        queue.appendleft(song)
        queue.rotate(target_index)
        await ctx.send(f"Moved song [{origin} -> {target}]: {song['query']}")

    @commands.command()
    async def clear(self, ctx):
        """Clears all songs on queue"""
        info = self.get_info(ctx)
        queue = info["queue"]
        queue.clear()
        await ctx.send("Cleared queue")

    @commands.command(aliases=["s"])
    async def skip(self, ctx):
        """Skips current song"""
        info = self.get_info(ctx)
        current = info["current"]
        ctx.voice_client.stop()
        if current is not None and not info["waiting"]:
            await ctx.send(f"Skipped: {current['query']}")

    @commands.command()
    async def loop(self, ctx, loop: typing.Optional[bool] = None):
        """Gets or sets queue looping"""
        info = self.get_info(ctx)
        if loop is None:
            await ctx.send(f"Queue {'is' if info['loop'] else 'is not'} looping")
            return
        info["loop"] = loop
        await ctx.send(f"Queue {'is now' if info['loop'] else 'is now not'} looping")

    @commands.command()
    @commands.is_owner()
    async def reschedule(self, ctx):
        """Reschedules the current guild onto the advancer task"""
        self.schedule(ctx, force=True)
        await ctx.send("Rescheduled")

    @local.before_invoke
    @stream.before_invoke
    async def ensure_connected(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                raise commands.CommandError("Author not connected to a voice channel")

    @pause.before_invoke
    @resume.before_invoke
    async def check_playing(self, ctx):
        await self.check_connected(ctx)
        if ctx.voice_client.source is None:
            raise commands.CommandError("Not playing anything right now")

    @remove.before_invoke
    @reschedule.before_invoke
    @skip.before_invoke
    @clear.before_invoke
    @volume.before_invoke
    async def check_connected(self, ctx):
        if ctx.voice_client is None:
            raise commands.CommandError("Not connected to a voice channel")

def setup(bot):
    bot.add_cog(Music(bot))

    # Suppress noise about console usage from errors
    bot._music_old_ytdl_bug_report_message = youtube_dl.utils.bug_reports_message
    youtube_dl.utils.bug_reports_message = lambda: ''

def teardown(bot):
    youtube_dl.utils.bug_reports_message = bot._music_old_ytdl_bug_report_message
