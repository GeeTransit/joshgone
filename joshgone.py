import os
import typing

import aiosqlite
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix=("%joshgone ", "%"), intents=intents)

@bot.event
async def on_ready():
    print(f"JoshGone logged on as {bot.user}.")
    print(f"SQLite version is {aiosqlite.sqlite_version}.")

@bot.event
async def on_guild_join(guild):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        await db.execute("INSERT INTO server (server_id, running) VALUES (?, ?);", (guild.id, True))
        await db.commit()

@bot.event
async def on_guild_remove(guild):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        await db.execute("DELETE FROM server WHERE server_id = ?;", (guild.id,))
        await db.commit()

@bot.command(name="reinit")
async def reinit_command(ctx):
    await on_guild_remove(ctx.guild)
    await on_guild_join(ctx.guild)
    await ctx.send("Reinitialized JoshGone.")

@bot.command(name="running")
async def running_command(ctx, run: bool = None):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        if run is None:
            async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                await on_guild_join(ctx.guild)
                async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                    row = await cursor.fetchone()
            running = bool(row[0])
            await ctx.send(f"JoshGone is currently {'running' if running else 'not running'}.")
        else:
            await db.execute("UPDATE server SET running = ? WHERE server_id = ?;", (run, ctx.guild.id))
            await db.commit()
            await ctx.send(f"JoshGone is now {'' if run else 'not '}running.")

@bot.group(name="emojis", pass_context=True, invoke_without_command=True)
async def emojis(ctx):
    await emojis_list(ctx)

@emojis.command(name="list")
async def emojis_list(ctx):
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

@emojis.command(name="add")
async def emojis_add(ctx, *emojis: typing.Union[discord.Emoji, str]):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        values = []
        for emoji in emojis:
            if isinstance(emoji, str):
                if len(emoji) == 1:
                    values.append((ctx.guild.id, emoji))
            elif emoji.id is not None:
                values.append((ctx.guild.id, emoji.id))
        await db.executemany("INSERT INTO removed_emoji VALUES (?, ?) ON CONFLICT DO NOTHING;", values)
        await db.commit()
        await ctx.send(f"Added {', '.join(map(str, emojis))} to removal list.")

@emojis.command(name="remove")
async def emojis_remove(ctx, *emojis: typing.Union[discord.Emoji, str]):
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

@emojis.command(name="clear")
async def emojis_clear(ctx):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        await db.execute("DELETE FROM removed_emoji WHERE server_id = ?;", (ctx.guild.id,))
        await db.commit()
        await ctx.send("Cleared removal list.")

@bot.group(name="allow", pass_context=True, invoke_without_command=True)
async def allow(ctx):
    await allow_list(ctx)

@allow.command(name="list")
async def allow_list(ctx):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        async with db.execute("SELECT user_id FROM allowed_user WHERE server_id = ?;", (ctx.guild.id,)) as cursor:
            users = [ctx.guild.get_member(row[0]) async for row in cursor]
        await ctx.send(f"JoshGone is currently ignoring {', '.join(user.name for user in users)}.")

@allow.command(name="add")
async def allow_add(ctx, *users: discord.Member):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        values = [(ctx.guild.id, user.id) for user in users]
        await db.executemany("INSERT INTO allowed_user VALUES (?, ?) ON CONFLICT DO NOTHING;", values)
        await db.commit()
        await ctx.send(f"Added {', '.join(user.name for user in users)} to allow list.")

@allow.command(name="remove")
async def allow_remove(ctx, *users: discord.Member):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        values = [(user.id, ctx.guild.id) for user in users]
        await db.executemany("DELETE FROM allowed_user WHERE user_id = ? AND server_id = ?;", values)
        await db.commit()
        await ctx.send(f"Removed {', '.join(user.name for user in users)} from allow list.")

@allow.command(name="clear")
async def allow_clear(ctx):
    async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
        await db.execute("DELETE FROM allowed_user WHERE server_id = ?;", (ctx.guild.id,))
        await db.commit()
        await ctx.send("Cleared allow list.")

@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
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

import math
import re
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

bot.run(os.environ["JOSHGONE_TOKEN"])
