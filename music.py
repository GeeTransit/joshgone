# Source: https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py

import asyncio

import discord
from discord.ext import commands

import youtube_dl

class Music(commands.Cog):
    _DEFAULT_YTDL_OPTS = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
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

    async def player_from_url(self, url, *, loop=None, stream=False):
        ytdl = youtube_dl.YoutubeDL(self.ytdl_opts)
        loop = loop or asyncio.get_event_loop()
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
    async def play(self, ctx, *, query):
        """Plays a file from the local filesystem"""
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        ctx.voice_client.play(source, after=lambda e: e and print(f'Player error: {e}'))
        await ctx.send(f"Now playing: {query}")

    @commands.command()
    @commands.is_owner()
    async def yt(self, ctx, *, url):
        """Plays from a url (almost anything youtube_dl supports)"""
        async with ctx.typing():
            player, data = await self.player_from_url(url)
            ctx.voice_client.play(player, after=lambda e: e and print(f'Player error: {e}'))
        await ctx.send(f"Now playing: {data.get('title')}")

    @commands.command()
    async def stream(self, ctx, *, url):
        """Streams from a url (same as yt, but doesn't predownload)"""
        async with ctx.typing():
            player, data = await self.player_from_url(url, stream=True)
            ctx.voice_client.play(player, after=lambda e: e and print(f'Player error: {e}'))
        await ctx.send(f"Now playing: {data.get('title')}")

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

    @commands.command()
    async def pause(self, ctx):
        """Pauses playing"""
        ctx.voice_client.pause()

    @commands.command()
    async def resume(self, ctx):
        """Resumes playing"""
        ctx.voice_client.resume()

    @commands.command()
    async def stop(self, ctx):
        """Stops playing"""
        ctx.voice_client.stop()

    @commands.command()
    async def leave(self, ctx):
        """Stops and disconnects the bot from voice"""
        if ctx.voice_client is None:
            return
        await ctx.voice_client.disconnect()

    @play.before_invoke
    @yt.before_invoke
    @stream.before_invoke
    async def ensure_stopped(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @pause.before_invoke
    @resume.before_invoke
    async def check_source(self, ctx):
        await self.check_connected(ctx)
        if ctx.voice_client.source is None:
            raise commands.CommandError("Not playing anything right now.")

    @stop.before_invoke
    async def check_connected(self, ctx):
        if ctx.voice_client is None:
            raise commands.CommandError("Author not connected to a voice channel.")

def setup(bot):
    bot.add_cog(Music(bot))

    # Suppress noise about console usage from errors
    bot._music_old_ytdl_bug_report_message = youtube_dl.utils.bug_reports_message
    youtube_dl.utils.bug_reports_message = lambda: ''

def teardown(bot):
    youtube_dl.utils.bug_reports_message = bot._music_old_ytdl_bug_report_message
