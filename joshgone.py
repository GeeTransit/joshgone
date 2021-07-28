import os

import discord
from discord.ext import commands

# These extensions are loaded automatically on startup
LOAD_ON_STARTUP = '''
    admin censor chant music database thicc gee remind split get relay solver
    sort repl info
'''.split()

# We need intents to resolve a name to a Member object
intents = discord.Intents.default()
intents.members = True

# Our prefix is % or @joshgone
bot = commands.Bot(command_prefix=commands.when_mentioned_or("%"), intents=intents)

# Load extensions
for module in LOAD_ON_STARTUP:
    bot.load_extension(module)
    print(f"Loaded {module}")
print(f"All extensions loaded: [{', '.join(LOAD_ON_STARTUP)}]")

bot.run(os.environ["JOSHGONE_TOKEN"])
