import asyncio
import asyncio.__main__ as asyncio_main
import os

# Imported so the REPL can use them
import discord
from discord.ext import commands

# Global variable to make sure the REPL isn't initialized twice
thread = None

# Starts the REPL using asyncio's code
async def _init_repl():
    global thread
    if thread is not None:
        return
    if not os.environ.get("JOSHGONE_REPL"):
        return
    variables = globals()
    loop = asyncio_main.loop = asyncio.get_running_loop()
    asyncio_main.console = asyncio_main.AsyncIOInteractiveConsole(variables, loop)
    asyncio_main.repl_future_interrupted = False
    asyncio_main.repl_future = None
    thread = asyncio_main.REPLThread()
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

def setup(bot):
    bot.add_listener(_init_repl, "on_ready")
