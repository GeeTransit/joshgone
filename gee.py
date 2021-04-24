import random
import re

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
        """Reply with something GeeTransit would say

        Usage:
            %gee                ->  random response
            %gee ...            ->  yes / no
            %gee X ...          ->  random number in [0, X]
            %gee X Y ...        ->  random number in [X, Y]
            %gee ... (or ...)+  ->  random choice
        """
        if arg is None:
            arg = ""
        splitted = arg.split()

        try:
            a = int(splitted[0])
        except IndexError:
            # Reply with a response if empty
            await ctx.send(random.choice(self.replies))
            return
        except ValueError:
            if "or" in splitted:
                # Reply with one of the choices
                await ctx.send(random.choice(re.split(r"\bor\b", arg)))
                return
            # Reply with yes or no to a question
            await ctx.send(random.choice(self.replies_question))
            return

        try:
            b = int(splitted[1])
        except (ValueError, IndexError):
            # Pick random number given a bound (0 to a)
            x = random.randint(*sorted((0, a)))
            await ctx.send(f"{x}")
            return

        if (a, b) == (69, 420):
            # Special numbers
            x = random.choice((69, 420))
        else:
            # Pick random number given two bounds (a to b)
            x = random.randint(*sorted((a, b)))
        await ctx.send(f"{x}")

def setup(bot):
    bot.add_cog(Gee(bot))
