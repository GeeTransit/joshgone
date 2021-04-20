import asyncio
import random

import discord
from discord.ext import commands

class Remind(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        if not hasattr(bot, "_remind_tasks"):
            bot._remind_tasks = {}
        self.tasks = bot._remind_tasks

    async def _send_after(self, ctx, seconds, name, arg):
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            self.tasks.pop(name, None)
            await ctx.send(f"Cancelled {name!r}")
        else:
            self.tasks.pop(name, None)
            await ctx.send(arg)

    @commands.command()
    async def remind(self, ctx, name: str, minutes: int, *, arg):
        """Sends the message after the specified number of minutes

        Set name to - or -- to get a randomized reminder name.
        """
        if name == "-" or name == "--":
            name = f"Reminder-{random.randint(100, 999)}"
        if name in self.tasks:
            raise ValueError(f"{name!r} already in tasks")
        task = asyncio.create_task(self._send_after(ctx, 60 * minutes, name, arg))
        self.tasks[name] = task
        await ctx.send(f"Added reminder with name {name!r}")

    @commands.command()
    async def cancel(self, ctx, *, name):
        """Cancels a previous reminder"""
        if name not in self.tasks:
            return
        self.tasks.pop(name).cancel()

    @commands.command()
    async def reminders(self, ctx):
        """Lists out the names of all reminders"""
        names = list(self.tasks)
        if not names:
            names = (None,)
        await ctx.send(f"Reminders: {', '.join(map(str, names))}")

def setup(bot):
    bot.add_cog(Remind(bot))
