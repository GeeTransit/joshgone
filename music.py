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

@dataclasses.dataclass
class Song:
    ty: str
    query: str

@dataclasses.dataclass
class InfoWrapper:
    id: int
    data: dict = dataclasses.field(repr=False)
    LATEST_VERSION: typing.ClassVar[int] = 3
    NAMES: typing.ClassVar[int] = "queue current waiting version loop processing".split()

    def __getattr__(self, name):
        try:
            return self.data[name][self.id]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in ("id", "data"):
            super().__setattr__(name, value)
        else:
            self.data[name][self.id] = value

    def __delattr__(self, name):
        if name in ("id", "data"):
            super().__delattr__(name)
        else:
            del self.data[name][self.id]

    def to_dict(self):
        return {name: getattr(self, name) for name in self.NAMES}

    def defined(self, name):
        return self.id in self.data[name]

    def fill(self):
        if not self.defined("version"):
            self.version = 0
        while (version := self.version) != self.LATEST_VERSION:
            getattr(self, f"_update{version}")()
            if version == self.version:
                raise TypeError(f"version unchanged: {version}")

    def _update0(self):
        if not self.defined("queue"):
            self.queue = deque()
        if not self.defined("current"):
            self.current = None
        if not self.defined("waiting"):
            self.waiting = False
        self.version = 1

    def _update1(self):
        if not self.defined("loop"):
            self.loop = False
        self.version = 2

    def _update2(self):
        if not self.defined("processing"):
            self.processing = False
        self.version = 3

class Music(commands.Cog):
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
    _DEFAULT_FFMPEG_OPTS = {
        'options': '-vn',
        # Source: https://stackoverflow.com/questions/66070749/
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    }

    def __init__(self, bot, *, ytdl_opts=_DEFAULT_YTDL_OPTS, ffmpeg_opts=_DEFAULT_FFMPEG_OPTS):
        self.bot = bot
        self.ytdl_opts = ytdl_opts
        self.ffmpeg_opts = ffmpeg_opts
        if not hasattr(bot, "_music_info"):
            bot._music_info = {}
        if not hasattr(bot, "_music_data"):
            bot._music_data = {}
        if not hasattr(bot, "_music_advance_queue"):
            bot._music_advance_queue = asyncio.Queue()
        self.infos = bot._music_info
        self.data = bot._music_data
        self.advance_queue = bot._music_advance_queue
        self.advance_task = None
        self.advancer.start()
        for name in InfoWrapper.NAMES:
            if name not in self.data:
                self.data[name] = {}

    def cog_unload(self):
        self.advancer.cancel()

    async def _play_local(self, query):
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        return source, query

    async def _play_stream(self, url):
        player, data = await self.player_from_url(url, stream=True)
        return player, data.get("title", url)

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

    @advancer.after_loop
    async def on_advancer_cancel(self):
        if self.advancer.is_being_cancelled():
            if self.advance_task is not None:
                self.advance_task.cancel()
                self.advance_task = None

    async def handle_advances(self):
        while True:
            item = await self.advance_queue.get()
            asyncio.create_task(self.handle_advance(item))

    async def handle_advance(self, item):
        ctx, error = item
        info = self.get_info(ctx)
        try:
            if info.processing:
                await asyncio.sleep(1)
                self.advance_queue.put_nowait(item)
                return
            info.processing = True
            if error is not None:
                await ctx.send(f"Player error: {error!r}")
            if ctx.voice_client is None:
                await ctx.send("Not connected to a voice channel anymore")
                await self.leave(ctx)
                return
            queue = info.queue
            if info.loop and info.current is not None:
                queue.append(info.current)
            info.current = None
            if queue:
                current = queue.popleft()
                if isinstance(current, tuple):
                    ty, query = current
                    current = Song(ty, query)
                info.current = current
                after = lambda error, ctx=ctx: self.schedule(ctx, error)
                async with ctx.typing():
                    source, title = await getattr(self, f"_play_{current.ty}")(current.query)
                    ctx.voice_client.play(source, after=after)
                await ctx.send(f"Now playing: {title}")
            else:
                await ctx.send(f"Queue empty")
        except Exception as e:
            await ctx.send(f"Internal Error: {e!r}")
            info.waiting = False
            await self.skip(ctx)
            self.schedule(ctx)
        finally:
            info.waiting = False
            info.processing = False

    def schedule(self, ctx, error=None, *, force=False):
        info = self.get_info(ctx)
        if force or not info.waiting:
            self.advance_queue.put_nowait((ctx, error))
            info.waiting = True

    def get_info(self, ctx):
        guild_id = ctx.guild.id
        wrapped = InfoWrapper(guild_id, self.data)
        if guild_id in self.infos:
            info = self.infos[guild_id]
            if not isinstance(info, dict):
                info = dataclasses.asdict(info)
            for name, value in info.items():
                setattr(wrapped, name, value)
        wrapped.fill()
        if guild_id in self.infos:
            del self.infos[guild_id]
        return wrapped

    def pop_info(self, ctx):
        wrapped = InfoWrapper(ctx.guild.id, self.data)
        for name in InfoWrapper.NAMES:
            if wrapped.defined(name):
                delattr(wrapped, name)
        return wrapped

    async def player_from_url(self, url, *, loop=None, stream=False):
        ytdl = youtube_dl.YoutubeDL(self.ytdl_opts)
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        audio = discord.FFmpegPCMAudio(filename, **self.ffmpeg_opts)
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
        queue = info.queue
        queue.append(Song("local", query))
        if info.current is None:
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
        queue = info.queue
        queue.append(Song("stream", url))
        if info.current is None:
            self.schedule(ctx)
        await ctx.send(f"Added to queue: stream {url}")

    @commands.command()
    async def shuffle(self, ctx):
        """Shuffles the queue"""
        info = self.get_info(ctx)
        queue = info.queue
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
            current = info.current
            if current is not None and not info.waiting:
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
            queue = info.queue
            length = len(queue)
            looping = info.loop
        queries = [song.query for song in queue]
        if not queries:
            queries = (None,)
        string = "\n".join(map(str, queries))
        await ctx.send(f"Queue [{length}]{' (looping)'*looping}:\n```\n{string}\n```")

    @commands.command()
    async def remove(self, ctx, position: int):
        """Removes a song on queue"""
        index = position
        if index > 0:
            index -= 1
        info = self.get_info(ctx)
        queue = info.queue
        if index < 0:
            index += len(queue)
        if not 0 <= index < len(queue):
            raise commands.CommandError(f"Index out of range [{position}]")
            return
        queue.rotate(-index)
        song = queue.popleft()
        queue.rotate(index)
        await ctx.send(f"Removed song [{position}]: {song.query}")

    @commands.command()
    async def clear(self, ctx):
        """Clears all songs on queue"""
        info = self.get_info(ctx)
        queue = info.queue
        queue.clear()
        await ctx.send("Cleared queue")

    @commands.command(aliases=["s"])
    async def skip(self, ctx):
        """Skips current song"""
        info = self.get_info(ctx)
        current = info.current
        ctx.voice_client.stop()
        if current is not None and not info.waiting:
            await ctx.send(f"Skipped: {current.query}")

    @commands.command()
    async def loop(self, ctx, loop: typing.Optional[bool] = None):
        """Gets or sets queue looping"""
        info = self.get_info(ctx)
        if loop is None:
            await ctx.send(f"Queue {'is' if info.loop else 'is not'} looping")
            return
        info.loop = loop
        await ctx.send(f"Queue {'is now' if info.loop else 'is now not'} looping")

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
