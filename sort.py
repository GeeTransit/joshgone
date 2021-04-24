import discord
from discord.ext import commands

class Sort(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sort")
    async def _sort(self, ctx, *args):
        r"""Sorts strings and outputs the final order

        Usage:
            %sort c b a     ->  sends a b c
            %sort a b c     ->  sends a b c
        """
        await ctx.send(" ".join(sorted(args)))

def setup(bot):
    bot.add_cog(Sort(bot))
