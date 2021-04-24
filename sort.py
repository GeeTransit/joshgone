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
            %sort 3 2 1     ->  sends 1 2 3
            %sort 1 2 3     ->  sends 1 2 3
        """
        # If all arguments can be ints, convert them
        try:
            args = [int(arg) for arg in args]
        except ValueError:
            try:
                args = [float(arg) for arg in args]
            except ValueError:
                pass
        await ctx.send(" ".join(map(str, sorted(args))))

def setup(bot):
    bot.add_cog(Sort(bot))
