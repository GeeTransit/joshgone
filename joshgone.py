import asyncio
import asyncio.__main__ as asyncio_main
import os
import re
import typing

import aiosqlite
import discord
from discord.ext import commands
from discord.utils import get

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix=("%joshgone ", "%"), intents=intents)
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

class Censor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            await db.execute("INSERT INTO server (server_id, running) VALUES (?, ?);", (guild.id, True))
            await db.commit()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            await db.execute("DELETE FROM server WHERE server_id = ?;", (guild.id,))
        await db.commit()

    @commands.command(name="reinit")
    async def reinit_command(self, ctx):
        await self.on_guild_remove(ctx.guild)
        await self.on_guild_join(ctx.guild)
        await ctx.send("Reinitialized JoshGone.")

    @commands.command(name="running", aliases=["r"])
    async def running_command(self, ctx, run: bool = None):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            if run is None:
                async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await self.on_guild_join(ctx.guild)
                    async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                        row = await cursor.fetchone()
                running = bool(row[0])
                await ctx.send(f"JoshGone is currently {'running' if running else 'not running'}.")
            else:
                await db.execute("UPDATE server SET running = ? WHERE server_id = ?;", (run, ctx.guild.id))
                await db.commit()
                await ctx.send(f"JoshGone is now {'' if run else 'not '}running.")

    @commands.group(name="emojis", aliases=["e"], pass_context=True, invoke_without_command=True)
    async def emojis(self, ctx):
        await self.emojis_list(ctx)

    @emojis.command(name="list", aliases=["l"])
    async def emojis_list(self, ctx):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            removed_emojis = []
            guild_emojis = {emoji.id: emoji for emoji in ctx.guild.emojis}
            async with db.execute("SELECT emoji_id FROM removed_emoji WHERE server_id = ?;", (ctx.guild.id,)) as cursor:
                async for row in cursor:
                    emoji_id = row[0]
                    if isinstance(emoji_id, str):
                        removed_emojis.append(emoji_id)
                    if emoji_id in guild_emojis:
                        removed_emojis.append(guild_emojis[emoji_id])
            await ctx.send(f"JoshGone is currently removing {', '.join(sorted(map(str, removed_emojis)))}.")

    @emojis.command(name="add", aliases=["a"])
    async def emojis_add(self, ctx, *emojis: typing.Union[discord.Emoji, str]):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            values = []
            for emoji in emojis:
                if isinstance(emoji, str):
                    if len(emoji) == 1:
                        values.append((ctx.guild.id, emoji))
                    else:
                        print(repr(emoji))
                        print(*map(ord, emoji))
                elif emoji.id is not None:
                    values.append((ctx.guild.id, emoji.id))
            await db.executemany("INSERT INTO removed_emoji VALUES (?, ?) ON CONFLICT DO NOTHING;", values)
            await db.commit()
            await ctx.send(f"Added {', '.join(map(str, emojis))} to removal list.")

    @emojis.command(name="remove", aliases=["r"])
    async def emojis_remove(self, ctx, *emojis: typing.Union[discord.Emoji, str]):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            values = []
            for emoji in emojis:
                if isinstance(emoji, str):
                    values.append((ctx.guild.id, emoji))
                elif emoji.id is not None:
                    values.append((ctx.guild.id, emoji.id))
            await db.executemany("DELETE FROM removed_emoji WHERE server_id = ? AND emoji_id = ?;", values)
            await db.commit()
            await ctx.send(f"Removed {', '.join(map(str, emojis))} from removal list.")

    @emojis.command(name="clear", aliases=["c"])
    async def emojis_clear(self, ctx):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            await db.execute("DELETE FROM removed_emoji WHERE server_id = ?;", (ctx.guild.id,))
            await db.commit()
            await ctx.send("Cleared removal list.")

    @commands.group(name="allow", aliases=["a"], pass_context=True, invoke_without_command=True)
    async def allow(self, ctx):
        await self.allow_list(ctx)

    @allow.command(name="list", aliases=["l"])
    async def allow_list(self, ctx):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            async with db.execute("SELECT user_id FROM allowed_user WHERE server_id = ?;", (ctx.guild.id,)) as cursor:
                users = [ctx.guild.get_member(row[0]) async for row in cursor]
            await ctx.send(f"JoshGone is currently ignoring {', '.join(user.name for user in users)}.")

    @allow.command(name="add", aliases=["a"])
    async def allow_add(self, ctx, *users: discord.Member):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            values = [(ctx.guild.id, user.id) for user in users]
            await db.executemany("INSERT INTO allowed_user VALUES (?, ?) ON CONFLICT DO NOTHING;", values)
            await db.commit()
            await ctx.send(f"Added {', '.join(user.name for user in users)} to allow list.")

    @allow.command(name="remove", aliases=["r"])
    async def allow_remove(self, ctx, *users: discord.Member):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            values = [(user.id, ctx.guild.id) for user in users]
            await db.executemany("DELETE FROM allowed_user WHERE user_id = ? AND server_id = ?;", values)
            await db.commit()
            await ctx.send(f"Removed {', '.join(user.name for user in users)} from allow list.")

    @allow.command(name="clear", aliases=["c"])
    async def allow_clear(self, ctx):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            await db.execute("DELETE FROM allowed_user WHERE server_id = ?;", (ctx.guild.id,))
            await db.commit()
            await ctx.send("Cleared allow list.")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user == self.bot.user:
            return
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (reaction.message.guild.id,)) as cursor:
                if not (row := await cursor.fetchone()) or not row[0]:
                    return
            async with db.execute("SELECT * FROM removed_emoji WHERE server_id = ? AND emoji_id = ? LIMIT 1;", (reaction.message.guild.id, reaction.emoji if isinstance(reaction.emoji, str) else reaction.emoji.id)) as cursor:
                if not await cursor.fetchone():
                    return
            async with db.execute("SELECT * FROM allowed_user WHERE server_id = ? AND user_id = ? LIMIT 1;", (reaction.message.guild.id, user.id)) as cursor:
                if await cursor.fetchone():
                    return
            await reaction.remove(user)

    async def process_message(self, message):
        author = message.author
        if author == self.bot.user:
            return
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (message.guild.id,)) as cursor:
                if not (row := await cursor.fetchone()) or not row[0]:
                    return
            async with db.execute("SELECT * FROM allowed_user WHERE server_id = ? AND user_id = ? LIMIT 1;", (message.guild.id, author.id)) as cursor:
                if await cursor.fetchone():
                    return
            for match in re.finditer(r"(?<!\\)<(a|):(\w+):(\d+)>", message.content):
                animated, name, id = match.groups()
                async with db.execute("SELECT * FROM removed_emoji WHERE server_id = ? AND emoji_id = ? LIMIT 1;", (message.guild.id, id)) as cursor:
                    if await cursor.fetchone():
                        break
            else:
                return
            await author.send(f"Message deleted:\n```\n{message.content}\n```")
            await message.delete()

ran = {}
@bot.before_invoke
async def before_invoke(ctx):
    ran[ctx.message] = True

@bot.event
async def on_message(message):
    if message.guild is None:
        return
    await bot.process_commands(message)
    if ran.pop(message, False):
        return
    censor = bot.get_cog("Censor")
    if censor is not None:
        await censor.process_message(message)

@bot.event
async def on_message_edit(before, after):
    if after.guild is None:
        return
    # await bot.process_commands(message)
    # if ran.pop(message, False):
        # return
    censor = bot.get_cog("Censor")
    if censor is not None:
        await censor.process_message(after)

BRUCECHANT = "okay guys so break is over stop playing games stop watching youtube stop doing cell phone stop watching anime"
@bot.command(name="brucechant", aliases=["b", "bc", "🅱️", "🇧"])
async def brucechant_commant(ctx, repeats: int = 5):
    for _ in range(repeats):
        async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
            async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                if not (row := await cursor.fetchone()) or not row[0]:
                    break
        await ctx.send(BRUCECHANT)
        await asyncio.sleep(0.5)

@bot.event
async def on_command_error(ctx, error):
    gee = get(bot.users, name="GeeTransit")
    await gee.send(f"Error:\n```{error!r}```")

import math
NUM = r"\d+(?:\.\d*)?"
VAR = r"(?!\d)\w"
SIGN = r"[+-]"
EXPR = fr"(?:({SIGN}) |())(?:(?:({NUM}) |())({VAR})|({NUM})())"  # sign, num, var

@bot.command(hidden=True)
async def solve(ctx, *, eq=""):
    infos = []  # Holds constant and coefficient of variable
    name = None  # Name of the variable

    # Loop through each expression and add them into `info`
    for expr in eq.split("="):
        info = [0, 0]  # [0] = coefficient, [1] = constant
        match = None  # Last match (for the empty expression checker)
        first = True  # Whether the term is the first term (can omit +/-)
        last = 0  # End index of the last match

        # Loop over each term. Raise an error when the substring between
        # matches contains something that's not a space.
        for match in re.finditer(EXPR.replace(" ", r"\s*"), expr):
            # Connecting substring must be whitespace only
            if expr[last:match.start()] and not expr[last:match.start()].isspace():
                raise ValueError(f"couldn't parse: {expr[last:match.start()]}")

            # Get the match's groups
            sign, num, var = filter(lambda i: i is not None, match.groups())
            # Only the first term can omit the +/-
            if not sign and not first:
                raise ValueError(f"missing sign for {num}{var}")
            # Default to 1 (such as when a variable is passed: 7+a)
            if not num:
                num = "1"

            # Turn the value into a Python int / float
            value = float(num) if "." in num else int(num)
            if sign == "-":
                value *= -1

            # Update expression info
            if var:
                # Only allow one variable is allowed for now
                if name is not None:
                    if name != var:
                        raise ValueError(f"more than one variable found: {name}, {var}")
                else:
                    name = var
                info[0] += value  # Add to coefficient
            else:
                info[1] += value  # Add to constant

            # Update first and last variables
            if first:
                first = False
            last = match.end()

        # Trailing substring must be whitespace only
        if expr[last:] and not expr[last:].isspace():
            raise ValueError(f"couldn't parse: {expr[last:]}")
        # The expression cannot be empty (at least one term needed)
        if match is None:
            raise ValueError(f"empty expression: {expr}")
        infos.append(info)  # Add to infos list

    if len(infos) == 1:
        # Single expression (no equals sign)
        var, const = infos[0]
        if var != 0:
            # Solve for the variable
            value = const / var
            if int(value) == value:
                value = int(value)
            await ctx.send(f"{name} = {value}")
        else:
            # Return the expression result
            await ctx.send(f"{const}")
        return

    # Multiple expressions
    first_var, first_const = infos[0]
    check = None
    for info in infos[1:]:
        var, const = info
        if not math.isclose(first_var, var):
            # Solve for the variable
            value = (const - first_const) / (first_var - var)
            # Check that the solved value equals previous values
            if check is not None:
                if not math.isclose(check, value):
                    raise ValueError(f"more than one possible value: {check}, {value}")
            else:
                check = value
        else:
            # Check that the constants equal eachother
            if not math.isclose(const, first_const):
                raise ValueError(f"more than one value: {first_const}, {const}")
    # Return solved value (variable or constant)
    if check is not None:
        if int(check) == check:
            check = int(check)
        await ctx.send(f"{name} = {check}")
    else:
        await ctx.send(f"{first_const}")

@solve.error
async def solve_error(ctx, error):
    await ctx.send(str(error))  # Sends error as a message (for debugging)

bot.add_cog(Censor(bot))
bot.run(os.environ["JOSHGONE_TOKEN"])
