import os
import discord

client = discord.Client()
running = False

@client.event
async def on_ready():
    print(f"JoshGone logged on as {client.user}")

@client.event
async def on_message(message):
    global running
    if message.author == client.user:
        return
    if message.content.startswith("%joshgone"):
        args = message.content.split()
        if len(args) == 1:
            await message.channel.send(f"JoshGone is currently {'running' if running else 'not running'}")
            return
        if len(args) == 2:
            if args[1] == "true":
                running = True
            elif args[1] == "false":
                running = False
        return

@client.event
async def on_reaction_add(reaction, user):
    global running
    if user == client.user:
        return
    if running and reaction.emoji.name == "josh":
        await reaction.remove(user)

client.run(os.environ["JOSHGONE_TOKEN"])
