import os
import discord

client = discord.Client()

@client.event
async def on_ready():
    print(f"JoshGone logged on as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith("%joshgone"):
        await message.channel.send("lmao boi this dont work just yet")

client.run(os.environ["JOSHGONE_TOKEN"])
