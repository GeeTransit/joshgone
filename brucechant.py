import os
import asyncio

import aiosqlite
from discord.ext import commands

class BruceChant(commands.Cog):
    BRUCECHANT = "okay guys so break is over stop playing games stop watching youtube stop doing cell phone stop watching anime"

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["b", "bc", "🅱️", "\\🅱️", "🇧", "\\🇧"], ignore_extra=False)
    async def brucechant(self, ctx, repeats: int = 5):
        for _ in range(repeats):
            async with aiosqlite.connect(os.environ["JOSHGONE_DB"]) as db:
                async with db.execute("SELECT running FROM server WHERE server_id = ? LIMIT 1;", (ctx.guild.id,)) as cursor:
                    if not (row := await cursor.fetchone()) or not row[0]:
                        break
            await ctx.send(self.BRUCECHANT)
            await asyncio.sleep(0.5)

def setup(bot):
    bot.add_cog(BruceChant(bot))
