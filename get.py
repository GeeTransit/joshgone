import asyncio

import discord
from discord.ext import commands

class Get(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="get")
    async def _get(self, ctx, *indices):
        r"""Gets a message from the channel's history

        Used to create a single command from multiple parts when self
        accept is on.

        Usage:
            %get 1      ->  sends last message
            %get 1 2    ->  sends last message \n second last message
            %get 1 1    ->  sends last message \n last message
        """
        if any(i <= 0 for i in indices):
            raise ValueError("all indices must be positive")
        if any(i > 100 for i in indices):
            raise ValueError("all indices must be less than or equal to 100")
        wanted = set(indices)
        messages = {}
        i = 0
        async for message in ctx.channel.history(limit=max(indices)+1):
            if i in wanted:
                messages[i] = message
            i += 1
        result = "\n".join(messages[i].content for i in indices)
        await ctx.send(result)

def setup(bot):
    bot.add_cog(Get(bot))
