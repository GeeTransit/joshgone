import asyncio
import asyncio.__main__ as asyncio_main
import os

import aiosqlite
import discord
from discord.ext import commands

# These extensions are loaded automatically on startup
LOAD_ON_STARTUP = ["censor", "brucechant", "music"]

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("%"), intents=intents)
thread = None

async def _init_repl():
    global thread
    if thread is not None:
        return
    variables = globals()
    loop = asyncio_main.loop = asyncio.get_running_loop()
    asyncio_main.console = asyncio_main.AsyncIOInteractiveConsole(variables, loop)
    asyncio_main.repl_future_interrupted = False
    asyncio_main.repl_future = None
    thread = asyncio_main.REPLThread()
    thread.daemon = True
    thread.start()

async def self_process(text_channel, content):
    message = await text_channel.send(content)
    return await process(message)

async def process(message):
    old_skip_check = bot._skip_check
    bot._skip_check = lambda x, y: False if x == y else old_skip_check(x, y)
    try:
        ctx = await bot.get_context(message)
        return await bot.invoke(ctx)
    finally:
        bot._skip_check = old_skip_check

@bot.event
async def on_ready():
    print(f"JoshGone logged on as {bot.user}.")
    print(f"SQLite version is {aiosqlite.sqlite_version}.")
    await _init_repl()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        error = error.__cause__ or error
    await ctx.send(f"Oops, an error occurred: `{error!r}`")

class Admin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    @commands.is_owner()
    async def load(self, ctx, *, module: str):
        self.bot.load_extension(module)
        await ctx.send("Extension loaded.")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, *, module: str):
        self.bot.unload_extension(module)
        await ctx.send("Extension unloaded.")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, *, module: str):
        self.bot.reload_extension(module)
        await ctx.send("Extension reloaded.")

bot.add_cog(Admin(bot))
for module in LOAD_ON_STARTUP:
    bot.load_extension(module)
    print(f"Loaded {module}")
print(f"All extensions loaded: [{', '.join(LOAD_ON_STARTUP)}]")
bot.run(os.environ["JOSHGONE_TOKEN"])
