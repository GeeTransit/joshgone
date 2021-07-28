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
command_prefix = commands.when_mentioned_or("%")

def run(token, **bot_kwargs):
    bot = commands.Bot(**bot_kwargs)

    # Load extensions
    for module in LOAD_ON_STARTUP:
        bot.load_extension(module)
        print(f"Loaded {module}")
    print(f"All extensions loaded: [{', '.join(LOAD_ON_STARTUP)}]")

    bot.run(token)

if __name__ == "__main__":
    run(
        os.environ["JOSHGONE_TOKEN"],
        command_prefix=command_prefix,
        intents=intents,
    )
