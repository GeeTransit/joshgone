import discord
from discord.ext import commands

class Thicc(commands.Cog):
    mapping = {}
    for original, target in zip(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿",
    ):
        mapping[original.upper()] = f"{target}\u200B"
        mapping[original.lower()] = f"{target}\u200B"
    for original, target in zip(
        "!?+-$",
        "❗❓➕➖️💲",
    ):
        mapping[original] = target
    for original, target in zip(
        "*#",
        ["*️⃣", "#️⃣"],
    ):
        mapping[original] = target
    for original, target in zip(
        "0123456789",
        "zero one two three four five six seven eight nine ten".split(),
    ):
        mapping[original] = f":{target}:"

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def thicc(self, ctx, *, message):
        """Convert letters to emojis"""
        await ctx.send("".join(self.mapping.get(char, char) for char in message))

def setup(bot):
    bot.add_cog(Thicc(bot))
