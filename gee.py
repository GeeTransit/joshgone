import random

import discord
from discord.ext import commands

class Gee(commands.Cog):
    replies = [
        "dang lol",
        "bruga",
        "lmao",
        "fax",
        "brug lol",
        "lol",
        "o ezpz",
        "brug tru",
        "damn",
        "dang",
        "tru",
        "lmaoo",
        "big fax",
        "o really",
        "ebic",
        "o dang",
        "wut lol",
        "wtf",
        "damn boi",
        "tooez",
        "pog",
        "lol aight",
        "o bruga",
        "sus",
        "ree",
        "yeebruh",
        "xD",
        "bruh",
        "frig",
        "pong",
        "lol pong",
        "ezpz",
        "bruh moment",
        "ez",
        "monke",
    ]
    replies_question = [
        "ye lol",
        "lol idk",
        "na lol",
        "ye ik",
        "na",
        "ye",
        "bruh na",
    ]

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["g"])
    async def gee(self, ctx, *, arg=None):
        """Reply with something GeeTransit would say"""
        if arg is None:
            arg = ""
        splitted = arg.split()

        # Reply with a response if empty
        if len(splitted) == 0:
            await ctx.send(random.choice(self.replies))
            return

        # Pick random number given a bound (0 to a)
        if len(splitted) == 1:
            try:
                a = int(splitted[0])
            except ValueError:
                pass
            else:
                x = random.randint(*sorted((0, a)))
                await ctx.send(f"{x}")
                return

        # Pick random number given two bounds (a to b)
        if len(splitted) == 2:
            try:
                a = int(splitted[0])
                b = int(splitted[1])
            except ValueError:
                pass
            else:
                x = random.randint(*sorted((a, b)))
                await ctx.send(f"{x}")
                return

        # Reply with yes or no to a question
        await ctx.send(random.choice(self.replies_question))

def setup(bot):
    bot.add_cog(Gee(bot))
