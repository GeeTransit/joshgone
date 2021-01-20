import os
import discord

client = discord.Client()
running = False
emojis = {"josh", "joshdeepfried"}
allow = {"GeeTransit"}  # Don't remove emojis from these users

@client.event
async def on_ready():
    print(f"JoshGone logged on as {client.user}")

@client.event
async def on_message(message):
    global running
    if message.author == client.user:
        return
    if message.content.startswith("%joshgone"):
        args = message.content.split()[1:]
        if len(args) == 0:
            await message.channel.send(f"JoshGone is currently {'running' if running else 'not running'}.")
            return
        if len(args) == 1:
            [command] = args
            if command == "help":
                await message.channel.send(
                    "Commands:\n"
                    "%joshgone running [true|false]\n"
                    "%joshgone emojis list\n"
                    "%joshgone emojis (add|remove) name\n"
                    "%joshgone allow list\n"
                    "%joshgone allow (add|remove) name\n"
                )
                return
            elif command == "emojis":
                args = command, "list"
            elif command == "allow":
                args = command, "list"
            elif command == "running":
                await message.channel.send(f"JoshGone is currently {'running' if running else 'not running'}.")
                return
            elif command in ("true", "false"):
                args = "running", command
            else:
                await message.channel.send(f"Unknown command {command}.")
                return
        if len(args) == 2:
            [command, arg] = args
            if command == "running":
                if arg == "true":
                    running = True
                    await message.channel.send(f"JoshGone is now running.")
                elif arg == "false":
                    running = False
                    await message.channel.send(f"JoshGone is now not running.")
                else:
                    await message.channel.send(f"Running command argument must be true or false, not {arg}.")
                return
            elif command == "emojis":
                if arg == "list":
                    await message.channel.send(f"JoshGone is currently removing {', '.join(sorted(emojis))}.")
                else:
                    await message.channel.send(f"Unknown {command} subcommand {arg}.")
                return
            elif command == "allow":
                if arg == "list":
                    await message.channel.send(f"JoshGone is currently ignoring {', '.join(sorted(allow))}.")
                else:
                    await message.channel.send(f"Unknown {command} subcommand {arg}.")
                return
        if len(args) == 3:
            [command, subcommand, arg] = args
            if command == "emojis":
                if subcommand == "add":
                    emojis.add(arg)
                    await message.channel.send(f"Added {arg} to removal list.")
                elif subcommand == "remove":
                    emojis.remove(arg)
                    await message.channel.send(f"Removed {arg} from removal list.")
                else:
                    await message.channel.send(f"Unknown {command} subcommand {subcommand}.")
                return
            elif command == "allow":
                if subcommand == "add":
                    allow.add(arg)
                    await message.channel.send(f"Added {arg} to allow list.")
                elif subcommand == "remove":
                    allow.remove(arg)
                    await message.channel.send(f"Removed {arg} from allow list.")
                else:
                    await message.channel.send(f"Unknown {command} subcommand {subcommand}.")
                return
        await message.channel.send(f"Unknown command %joshgone {' '.join(args)}.")
        return

@client.event
async def on_reaction_add(reaction, user):
    global running
    if user == client.user:
        return
    if running and user.name not in allow and reaction.emoji.name in emojis:
        await reaction.remove(user)

client.run(os.environ["JOSHGONE_TOKEN"])
