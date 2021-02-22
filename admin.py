from discord.ext import commands

class Admin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    @commands.is_owner()
    async def load(self, ctx, *, module: str):
        self.bot.load_extension(module)
        await ctx.send("Extension loaded.")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, *, module: str):
        self.bot.unload_extension(module)
        await ctx.send("Extension unloaded.")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, *, module: str):
        self.bot.reload_extension(module)
        await ctx.send("Extension reloaded.")

    @commands.command(name="list", hidden=True)
    @commands.is_owner()
    async def list_(self, ctx):
        extensions = ", ".join(self.bot.extensions)
        await ctx.send(f"Extensions loaded: [{extensions}]")

def setup(bot):
    bot.add_cog(Admin(bot))
