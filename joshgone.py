import os

import aiosqlite
import discord
from discord.ext import commands

# These extensions are loaded automatically on startup
LOAD_ON_STARTUP = '''
    admin censor chant music database thicc gee remind split get relay solver
    sort
'''.split()

# We need intents to resolve a name to a Member object
intents = discord.Intents.default()
intents.members = True

# Our prefix is % or @joshgone
bot = commands.Bot(command_prefix=commands.when_mentioned_or("%"), intents=intents)

# Global variable to make sure extensions aren't initialized twice
started = False

@bot.event
async def on_ready():
    global started
    # Some debug info
    print(f"JoshGone logged on as {bot.user}.")
    print(f"SQLite version is {aiosqlite.sqlite_version}.")
    # Check if extensions are already initialized
    if started:
        return
    started = True
    # Load extensions
    for module in LOAD_ON_STARTUP:
        bot.load_extension(module)
        print(f"Loaded {module}")
    print(f"All extensions loaded: [{', '.join(LOAD_ON_STARTUP)}]")

@bot.event
async def on_command_error(ctx, error):
    # Unpack the error for cleaner error messages
    if isinstance(error, commands.CommandInvokeError):
        error = error.__cause__ or error
    try:
        await ctx.send(f"Oops, an error occurred: `{error!r}`")
    except Exception:
        print(f"Error: {error!r}")
        raise

# A separate extension handles the REPL
bot.load_extension("repl")

bot.run(os.environ["JOSHGONE_TOKEN"])
