import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

class MapsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.ping_task.start()

    def cog_unload(self):
        self.ping_task.cancel()

    @tasks.loop(minutes=1.0)
    async def ping_task(self):
        # Fetch maps run info from the database based on the scheduled message ID
        self.bot.db_cursor.execute('SELECT * FROM maps_runs WHERE message_id=?', (message_id,))
        maps_run = self.bot.db_cursor.fetchone()

        if maps_run:
            # Calculate the time 20 minutes before the timestamp
            timestamp = datetime.datetime.strptime(maps_run['timestamp'], '%Y-%m-%d %H:%M:%S')
            ping_time = timestamp - datetime.timedelta(minutes=20)

            # Check if it's time to ping
            current_time = datetime.now(timezone.utc)
            if current_time >= ping_time:
                # Fetch the joined users
                joined_user_ids = maps_run['user_ids'].split(',')
                joined_users = [f"<@{user_id}>" for user_id in joined_user_ids if user_id]

                # Create an embed with the ping message
                embed = discord.Embed(
                    title="Maps Run Reminder",
                    description=f"The maps run will start in 20 minutes. Are you ready?\nJoined Users: {' '.join(joined_users)}",
                    color=0xff0000
                )

                # Find the message to ping
                message_id = maps_run['message_id']
                channel_id = self.bot.config['events_channel_id']
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.channel.send(embed=embed)
                    except discord.NotFound:
                        pass