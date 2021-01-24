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
                values.append((ctx.guild.id, emoji))
            elif emoji.is_usable() and emoji.id is not None:
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
                if len(emoji) == 1:
                    values.append((ctx.guild.id, emoji))
            elif emoji.is_usable() and emoji.id is not None:
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

bot.run(os.environ["JOSHGONE_TOKEN"])
