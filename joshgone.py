import os
import discord
from discord.ext import commands

bot = commands.Bot(command_prefix=["%joshgone ", "%"])
running = False
emojis_set = set()
allow_set = set()  # Don't remove emojis from these users

@bot.event
async def on_ready():
    print(f"JoshGone logged on as {bot.user}.")

@bot.command(name="running")
async def running_command(ctx, run: bool = None):
    global running
    if run is None:
        await ctx.send(f"JoshGone is currently {'running' if running else 'not running'}.")
    elif run:
        running = True
        await ctx.send(f"JoshGone is now running.")
    else:
        running = False
        await ctx.send(f"JoshGone is now not running.")

@bot.group(name="emojis", pass_context=True, invoke_without_command=True)
async def emojis(ctx):
    await emojis_list(ctx)

@emojis.command(name="list")
async def emojis_list(ctx):
    await ctx.send(f"JoshGone is currently removing {', '.join(sorted(map(str, emojis_set)))}.")

@emojis.command(name="add")
async def emojis_add(ctx, emoji: discord.Emoji):
    emojis_set.add(emoji)
    await ctx.send(f"Added {emoji} to removal list.")

@emojis.command(name="remove")
async def emojis_remove(ctx, emoji: discord.Emoji):
    emojis_set.remove(emoji)
    await ctx.send(f"Removed {emoji} from removal list.")

@bot.group(name="allow", pass_context=True, invoke_without_command=True)
async def allow(ctx):
    await allow_list(ctx)

@allow.command(name="list")
async def allow_list(ctx):
    await ctx.send(f"JoshGone is currently ignoring {', '.join(sorted(allow_set))}.")

@allow.command(name="add")
async def allow_add(ctx, arg):
    allow_set.add(arg)
    await ctx.send(f"Added {arg} to allow list.")

@allow.command(name="remove")
async def allow_remove(ctx, arg):
    allow_set.remove(arg)
    await ctx.send(f"Removed {arg} from allow list.")

@bot.event
async def on_reaction_add(reaction, user):
    global running
    if user == bot.user:
        return
    if running and user.name not in allow_set and reaction.emoji in emojis_set:
        await reaction.remove(user)

bot.run(os.environ["JOSHGONE_TOKEN"])
