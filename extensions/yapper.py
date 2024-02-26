def setup(bot):
    if not hasattr(bot, "yapper_gifs"):
        bot.yapper_gifs = [
            "https://tenor.com/view/guy-arguing-guy-talking-to-wall-talking-brick-wall-gif-18667615",
            "https://tenor.com/view/yapping-yapping-level-today-catastrophic-yapanese-gif-13513208407930173397",
        ]
    if not hasattr(bot, "yapper_chance"):
        bot.yapper_chance = 1/20
    @bot.listen()
    async def on_message(msg):
        import random
        if random.random() >= bot.yapper_chance:
            return  # only run this sometimes
        async for message in msg.channel.history(limit=5):
            if message.author != msg.author:
                return  # someone else sent a msg
            if (msg.created_at - message.created_at).seconds > 30*60:
                return  # message too long ago
        await msg.channel.send(random.choice(bot.yapper_gifs), delete_after=2)
    return bot.wrap_async(None)
