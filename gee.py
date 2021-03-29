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

    @commands.command()
    async def gee(self, ctx, *, arg=None):
        """Reply with something GeeTransit would say"""
        if arg is None:
            await ctx.send(random.choice(self.replies))
        else:
            await ctx.send(random.choice(self.replies_question))

def setup(bot):
    bot.add_cog(Gee(bot))
