# Source: https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py

import asyncio
from collections import deque

import discord
from discord.ext import commands

import youtube_dl

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
        if not hasattr(bot, "_music_advance_queue"):
            bot._music_advance_queue = asyncio.Queue()
        self.infos = bot._music_info
        self.advance_queue = bot._music_advance_queue
        self.advance_task = asyncio.create_task(self.handle_advances(), name="music_advancer")

    def cog_unload(self):
        self.advance_task.cancel()

    async def _play_local(self, query):
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        return source, query

    async def _play_stream(self, url):
        player, data = await self.player_from_url(url, stream=True)
        return player, data.get("title", url)

    async def handle_advances(self):
        while True:
            ctx, error = await self.advance_queue.get()
            info = self.get_info(ctx)
            info["current"] = None
            if error is not None:
                await ctx.send(f"Player error: {error!r}")
            queue = info["queue"]
            if queue:
                ty, query = info["current"] = queue.popleft()
                after = lambda error, ctx=ctx: self.schedule(ctx, error)
                try:
                    async with ctx.typing():
                        source, title = await getattr(self, f"_play_{ty}")(query)
                        ctx.voice_client.play(source, after=after)
                    await ctx.send(f"Now playing: {title}")
                except Exception as e:
                    await ctx.send(f"Internal Error: {e!r}")
                    info["waiting"] = False
                    await self.skip(ctx)
                    self.schedule(ctx)
            else:
                await ctx.send(f"Queue empty.")
            info["waiting"] = False

    def schedule(self, ctx, error=None, *, force=False):
        info = self.get_info(ctx)
        if force or not info["waiting"]:
            self.advance_queue.put_nowait((ctx, error))
            info["waiting"] = True

    def get_info(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.infos:
             self.infos[guild_id] = {}
        info = self.infos[guild_id]
        if "queue" not in info:
            info["queue"] = deque()
        if "current" not in info:
            info["current"] = None
        if "waiting" not in info:
            info["waiting"] = False
        return info

    def pop_info(self, ctx):
        return self.infos.pop(ctx.guild.id, None)

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
        queue = info["queue"]
        queue.append(("local", query))
        if info["current"] is None:
            self.schedule(ctx)
        await ctx.send(f"Added to queue: local {query}")

    @commands.command(aliases=["yt", "play"])
    async def stream(self, ctx, *, url):
        """Plays from a url (almost anything youtube_dl supports)"""
        info = self.get_info(ctx)
        queue = info["queue"]
        queue.append(("stream", url))
        if info["current"] is None:
            self.schedule(ctx)
        await ctx.send(f"Added to queue: stream {url}")

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
            return await ctx.send("Not connected to a voice channel.")
        if int(volume) == volume:
            volume = int(volume)
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

    @commands.command()
    async def current(self, ctx):
        """Shows the current song"""
        query = None
        if ctx.voice_client is not None:
            info = self.get_info(ctx)
            current = info["current"]
            if current is not None and not info["waiting"]:
                ty, query = current
        await ctx.send(f"Current: {query}")

    @commands.command()
    async def queue(self, ctx):
        """Shows the songs on queue"""
        queue = ()
        length = 0
        if ctx.voice_client is not None:
            info = self.get_info(ctx)
            queue = info["queue"]
            length = len(queue)
        queries = [query for ty, query in queue]
        if not queries:
            queries = (None,)
        string = "\n".join(map(str, queries))
        await ctx.send(f"Queue [{length}]:\n```\n{string}\n```")

    @commands.command()
    async def remove(self, ctx, position: int):
        """Removes a song on queue"""
        index = position
        if index > 0:
            index -= 1
        info = self.get_info(ctx)
        queue = info["queue"]
        if index < 0:
            index += len(queue)
        if not 0 <= index < len(queue):
            raise commands.CommandError(f"Index out of range [{position}].")
            return
        queue.rotate(-index)
        ty, query = queue.popleft()
        queue.rotate(index)
        await ctx.send(f"Removed song [{position}]: {query}")

    @commands.command()
    async def clear(self, ctx):
        """Clears all songs on queue"""
        info = self.get_info(ctx)
        queue = info["queue"]
        queue.clear()
        await ctx.send("Cleared queue.")

    @commands.command()
    async def skip(self, ctx):
        """Skips current song"""
        info = self.get_info(ctx)
        current = info["current"]
        ctx.voice_client.stop()
        if current is not None and not info["waiting"]:
            ty, query = current
            await ctx.send(f"Skipped: {query}")

    @commands.command()
    @commands.is_owner()
    async def reschedule(self, ctx):
        """Reschedules the current guild onto the advancer task"""
        self.schedule(ctx, force=True)
        await ctx.send("Rescheduled.")

    @local.before_invoke
    @stream.before_invoke
    async def ensure_connected(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

    @pause.before_invoke
    @resume.before_invoke
    async def check_playing(self, ctx):
        await self.check_connected(ctx)
        if ctx.voice_client.source is None:
            raise commands.CommandError("Not playing anything right now.")

    @remove.before_invoke
    @reschedule.before_invoke
    @skip.before_invoke
    @clear.before_invoke
    @volume.before_invoke
    async def check_connected(self, ctx):
        if ctx.voice_client is None:
            raise commands.CommandError("Not connected to a voice channel.")

def setup(bot):
    bot.add_cog(Music(bot))

    # Suppress noise about console usage from errors
    bot._music_old_ytdl_bug_report_message = youtube_dl.utils.bug_reports_message
    youtube_dl.utils.bug_reports_message = lambda: ''

def teardown(bot):
    youtube_dl.utils.bug_reports_message = bot._music_old_ytdl_bug_report_message
