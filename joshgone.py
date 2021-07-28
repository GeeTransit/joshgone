import os

import aiosqlite
import discord
from discord.ext import commands

# These extensions are loaded automatically on startup
LOAD_ON_STARTUP = '''
    admin censor chant music database thicc gee remind split get relay solver
    sort repl
'''.split()

# We need intents to resolve a name to a Member object
intents = discord.Intents.default()
intents.members = True

# Our prefix is % or @joshgone
bot = commands.Bot(command_prefix=commands.when_mentioned_or("%"), intents=intents)

@bot.event
async def on_ready():
    # Some debug info
    print(f"JoshGone logged on as {bot.user}.")
    print(f"SQLite version is {aiosqlite.sqlite_version}.")

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

# Load extensions
for module in LOAD_ON_STARTUP:
    bot.load_extension(module)
    print(f"Loaded {module}")
print(f"All extensions loaded: [{', '.join(LOAD_ON_STARTUP)}]")

bot.run(os.environ["JOSHGONE_TOKEN"])
