import asyncio
import math
import typing

import discord
from discord.ext import commands

class Split(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="split")
    async def _split(self, ctx, delay: typing.Optional[float] = 0.5, *, lines):
        """Splits and sends the argument's lines as separate messages

        Used to package multiple commands into a single command when self
        accept is on.

        `delay` specifies the number of seconds between messages
        """
        if not math.isfinite(delay):
            raise ValueError(f"{delay!r} is not finite")
        for line in lines.splitlines():
            await ctx.send(line)
            await asyncio.sleep(delay)

def setup(bot):
    bot.add_cog(Split(bot))
