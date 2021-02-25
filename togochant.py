import os
import asyncio

import aiosqlite
from discord.ext import commands

class TogoChant(commands.Cog):
    TOGOCHANT = '''
Togohogo1 is not getting enough clout.
He needs to be praised and worshipped.
Can't be wasting ur time paying for ur taxes when u can pay him for being pro.
Its best if all your money goes to him since its for a good cause.
'''
    TOGONOOB = '''
Togohogo1 is getting too much clout.
He needs to be abandoned and forgotten now.
Can't be wasting ur time paying a noob when u can pay me for being better than you.
Its best if all your money goes to me since its for a good cause - its for charity.
Aight imma stop rapping, imma cut to the chase.
My boi Togohogo1 shouldn't be in first place.
'''

    def __init__(self, bot):
        self.bot = bot

    @commands.command(ignore_extra=False)
    async def togochant(self, ctx, repeats: int = 5):
        for _ in range(repeats):
            async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
                async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                    if not (row := await cursor.fetchone()) or not row[0]:
                        break
            await ctx.send(self.TOGOCHANT)
            await asyncio.sleep(0.5)

    @commands.command(ignore_extra=False)
    async def togonoob(self, ctx, repeats: int = 5):
        for _ in range(repeats):
            async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
                async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                    if not (row := await cursor.fetchone()) or not row[0]:
                        break
            await ctx.send(self.TOGONOOB)
            await asyncio.sleep(0.5)

def setup(bot):
    bot.add_cog(TogoChant(bot))
