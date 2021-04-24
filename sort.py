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
        try:
            # If all arguments can be ints, convert them
            result = sorted(args, key=int)
        except ValueError:
            try:
                # If all arguments can be floats, convert them
                result = sorted(args, key=float)
            except ValueError:
                # Otherwise, just use lexicographical order
                result = sorted(args)
        await ctx.send(" ".join(result))

def setup(bot):
    bot.add_cog(Sort(bot))
> ** test **
%h1 g-add-next

[CODE]
%chants add g-bold
    %lines 3
        - **
        %get 1.2 5 1.2
        %h1 g-bold-next

[DOCS]
%chants add g-bold-man
```
Usage:
    > text
    > %lines %h1 g-bold
    ...
    > ** text **
    > %h1 g-bold-next
```



[RUNNING]
> 5 6
%lines %h1 a-plus-b
%h1 a-plus-b
%lines 3 (%chants update g-add-next %h1 a-plus-b-1, %get 6, %lines %h1 g-add)
%chants update g-add-next %h1 a-plus-b-1
> Updated chant g-add-next
%get 6
> 5 6
%lines %h1 g-add
...
> 11
> %h1 g-add-next
%h1 a-plus-b-1
%lines 3 (%chants remove g-bold-next, %get 6, %lines %h1 g-bold)
%chants remove g-bold-next
> Removed chant g-bold-next
%get 6
> 11
%lines %h1 g-bold
...
> ** 11 **
> %h1 g-bold-next
%h1 a-plus-b-2
%get 3
> ** 11 **

[CODE]
%chants add a-plus-b
    %lines 3
        %chants update g-add-next %h1 a-plus-b-1
        %get 6
        %lines %h1 g-add
%chants add a-plus-b-1
    %lines 3
        %chants update g-bold-next %h1 a-plus-b-2
        %get 6
        %lines %h1 g-bold
%chants add a-plus-b-2
    %get 3

[DOCS]
%chants add a-plus-b-man
```
Usage:
    > 1 2
    > %lines %h1 a-plus-b
    ...
    > ** 3 **
```



[RUNNING]
> 5 6
%lines %h1 g-min
%h1 a-plus-b
%lines 3 (%chants update g-add-next %h1 a-plus-b-1, %get 6, %lines %h1 g-add)
%chants update g-add-next %h1 a-plus-b-1
> Updated chant g-add-next
%get 6
> 5 6
%lines %h1 g-add
...
> 11
> %h1 g-add-next
%h1 a-plus-b-1
%lines 3 (%chants remove g-bold-next, %get 6, %lines %h1 g-bold)
%chants remove g-bold-next
> Removed chant g-bold-next
%get 6
> 11
%lines %h1 g-bold
...
> ** 11 **
> %h1 g-bold-next
%h1 a-plus-b-2
%get 3
> ** 11 **

[CODE]
%chants add a-plus-b
    %lines 3
        %chants update g-add-next %h1 a-plus-b-1
        %get 6
        %lines %h1 g-add
%chants add a-plus-b-1
    %lines 3
        %chants update g-bold-next %h1 a-plus-b-2
        %get 6
        %lines %h1 g-bold
%chants add a-plus-b-2
    %get 3

[DOCS]
%chants add a-plus-b-man
```
Usage:
    > 1 2
    > %lines %h1 a-plus-b
    ...
    > ** 3 **
```
'''
