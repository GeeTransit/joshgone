import asyncio
import asyncio.__main__ as asyncio_main
import os

# Imported so the REPL can use them
import discord
from discord.ext import commands


# Subclass of REPLThread that doesn't stop the loop (joshgone.py handles that)
# Adapted from: Python39/Lib/asyncio/__main__.py
import sys
import warnings

class REPLNoStopThread(asyncio_main.REPLThread):

    def run(self):
        try:
            banner = (
                f'asyncio REPL {sys.version} on {sys.platform}\n'
                f'Use "await" directly instead of "asyncio.run()".\n'
                f'Type "help", "copyright", "credits" or "license" '
                f'for more information.\n'
                f'{getattr(sys, "ps1", ">>> ")}import asyncio'
            )

            asyncio_main.console.interact(
                banner=banner,
                exitmsg='exiting asyncio REPL...')
        finally:
            warnings.filterwarnings(
                'ignore',
                message=r'^coroutine .* was never awaited$',
                category=RuntimeWarning)

            # The main thread will stop it. Otherwise, this chokes the cleanup
            # code in discord.py.
            # loop.call_soon_threadsafe(loop.stop)


# Global variable to make sure the REPL isn't initialized twice
thread = None

# Starts the REPL using asyncio's code
async def _init_repl():
    global thread
    if thread is not None:
        return
    if not int(os.environ.get("JOSHGONE_REPL", "0")):
        return
    variables = globals()
    loop = asyncio_main.loop = asyncio.get_running_loop()
    asyncio_main.console = asyncio_main.AsyncIOInteractiveConsole(variables, loop)
    asyncio_main.repl_future_interrupted = False
    asyncio_main.repl_future = None
    thread = REPLNoStopThread()
    thread.daemon = True
    thread.start()

# Utility method to send a message that will be processed using `process`
async def self_process(text_channel, content):
    message = await text_channel.send(content)
    return await process(message)

# Utility method to temporarily disable the bot check and to process the message
async def process(message):
    old_skip_check = bot._skip_check
    bot._skip_check = lambda x, y: False if x == y else old_skip_check(x, y)
    try:
        ctx = await bot.get_context(message)
        return await bot.invoke(ctx)
    finally:
        bot._skip_check = old_skip_check

def setup(_bot):
    global bot
    bot = _bot
    bot.add_listener(_init_repl, "on_ready")
