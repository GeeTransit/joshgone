# Source: https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py

import asyncio
import dataclasses
import random
import typing
import traceback
from collections import deque

import discord
from discord.ext import commands
from discord.ext import tasks

import youtube_dl

import patched_player

# Holds a song request
@dataclasses.dataclass
class Song:
    ty: str  # can be "local" or "stream"
    query: str  # the string passed to Music._play_{ty}

# Wraps the info for a guild with __get/set/delattr__ methods
@dataclasses.dataclass
class InfoWrapper:
    id: int  # guild id
    data: dict = dataclasses.field(repr=False)  # bot._music_data
    LATEST_VERSION: typing.ClassVar[int] = 3  # version to upgrade to

    def __post_init__(self):
        if self.id not in self.data:
            self.data[self.id] = {}

    def __getattr__(self, name):
        try:
            return self.data[self.id][name]
        except KeyError:
            raise AttributeError(name)
    __getitem__ = __getattr__

    def __setattr__(self, name, value):
        if name in ("id", "data"):
            # This is special cased or else it would assign it to the data dict
            super().__setattr__(name, value)
        else:
            self.data[self.id][name] = value
    __setitem__ = __setattr__

    def __delattr__(self, name):
        if name in ("id", "data"):
            # Special cased for the same reason as in __setattr__
            super().__delattr__(name)
        else:
            del self.data[self.id][name]
    __delitem__ = __delattr__

    # Returns a dict with all info for debugging purposes. Modifying this dict won't update the data dict
    def to_dict(self):
        return dict(self.data[self.id])

    # Returns whether the name is in the data dict
    def defined(self, name):
        return name in self.data[self.id]

    # Updates the info to the latest version's format. This calls the _update{version} methods until the latest version is reached.
    def fill(self):
        if not self.defined("version"):
            self["version"] = 0
        while (version := self["version"]) != self.LATEST_VERSION:
            getattr(self, f"_update{version}")()
            if version == self["version"]:
                raise TypeError(f"version unchanged: {version}")

    # - Update methods
    def _update0(self):
        if not self.defined("queue"):
            self["queue"] = deque()
        if not self.defined("current"):
            self["current"] = None
        if not self.defined("waiting"):
            self["waiting"] = False
        self["version"] = 1

    def _update1(self):
        if not self.defined("loop"):
            self["loop"] = False
        self["version"] = 2

    def _update2(self):
        if not self.defined("processing"):
            self["processing"] = False
        self["version"] = 3

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

    def __init__(self, bot, *, ytdl_opts=_DEFAULT_YTDL_OPTS, ffmpeg_opts=_DEFAULT_FFMPEG_OPTS):
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
                await ctx.send(f"Player error: {error!r}")
            # If we aren't connected anymore, notify and leave
            if ctx.voice_client is None:
                await ctx.send("Not connected to a voice channel anymore")
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
                if isinstance(current, tuple):
                    ty, query = current
                    current = Song(ty, query)
                info["current"] = current
                # Get an audio source and play it
                after = lambda error, ctx=ctx: self.schedule(ctx, error)
                async with ctx.typing():
                    source, title = await getattr(self, f"_play_{current.ty}")(current.query)
                    ctx.voice_client.play(source, after=after)
                await ctx.send(f"Now playing: {title}")
            else:
                await ctx.send(f"Queue empty")
        except Exception as e:
            await ctx.send(f"Internal Error: {e!r}")
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
        wrapped = InfoWrapper(guild_id, self.data)
        if "queue" not in wrapped:
            wrapped["queue"] = deque()
            wrapped["current"] = None
            wrapped["waiting"] = False
            wrapped["loop"] = False
            wrapped["processing"] = False
            wrapped["version"] = 3
        return wrapped

    # Helper function to remove the info for a guild
    def pop_info(self, ctx):
        wrapped = InfoWrapper(ctx.guild.id, self.data)
        self.data.pop(ctx.guild.id, None)
        return wrapped

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

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""
        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)
        await channel.connect()

    @commands.command()
    @commands.is_owner()
    async def local(self, ctx, *, query):
        """Plays a file from the local filesystem"""
        info = self.get_info(ctx)
        queue = info["queue"]
        queue.append(Song("local", query))
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
        info = self.get_info(ctx)
        queue = info["queue"]
        ty = "local" if url == "coco.mp4" else "stream"
        queue.append(Song(ty, url))
        if info["current"] is None:
            self.schedule(ctx)
        await ctx.send(f"Added to queue: {ty} {url}")

    @commands.command()
    async def _add_playlist(self, ctx, *, url):
        """Adds all songs in a playlist to the queue"""
        if len(url) > 100:
            raise ValueError("url too long (length over 100)")
        if not url.isprintable():
            raise ValueError(f"url not printable: {url!r}")
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
            queue.append(Song("stream", url))
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
                query = current.query
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
                paginator.add_line(f"{i}: {song.query}")
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
        await ctx.send(f"Removed song [{position}]: {song.query}")

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
        await ctx.send(f"Moved song [{origin} -> {target}]: {song.query}")

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
            await ctx.send(f"Skipped: {current.query}")

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
                await ctx.send("You are not connected to a voice channel")
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
