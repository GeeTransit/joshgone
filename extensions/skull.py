def setup(B):
 @B.listen()
 async def on_message(M):"💀"in M.content and await M.channel.send("http://tenor.com/view/10107813",delete_after=2)
 return bot.wrap_async(None)
