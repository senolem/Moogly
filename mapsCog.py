import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from moogly import BotClient

class MapsCog(commands.Cog):
    def __init__(self, bot: BotClient):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.ping_task.start()

    def cog_unload(self):
        self.ping_task.cancel()

    @tasks.loop(minutes=1.0)
    async def ping_task(self):
        # Fetch maps runs that have not been pinged yet
        self.bot.db_cursor.execute('SELECT * FROM maps_runs WHERE pinged=0')
        maps_runs = self.bot.db_cursor.fetchall()

        if not maps_runs:
            return

        current_time = datetime.now(timezone.utc)
        
        for maps_run in maps_runs:
            # Extract timestamp and calculate ping time
            timestamp = datetime.strptime(maps_run[1], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            ping_time = timestamp - timedelta(minutes=20)

            if current_time >= ping_time:
                # Fetch the joined users
                joined_user_ids = maps_run[3].split(',')
                joined_users = [f"<@{user_id}>" for user_id in joined_user_ids if user_id]

                # Create an embed with the ping message
                embed = discord.Embed(
                    title="Maps Run Reminder",
                    description=f"The maps run will start in 20 minutes. Are you ready?\nJoined Users: {' '.join(joined_users)}",
                    color=0xff0000
                )

                # Find the message to ping
                message_id = maps_run[0]
                channel_id = self.bot.config['events_channel_id']
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.channel.send(embed=embed)

                        # Update the pinged status to true
                        self.bot.db_cursor.execute('UPDATE maps_runs SET pinged=1 WHERE message_id=?', (message_id,))
                        self.bot.db_conn.commit()

                    except discord.NotFound:
                        pass

# Add the cog to the bot
async def setup(bot):
    await bot.add_cog(MapsCog(bot))
