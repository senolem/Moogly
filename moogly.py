import discord
from discord.ext import commands, tasks
import json
import sqlite3
import traceback
import os
from datetime import datetime, timezone, timedelta

class BotClient(commands.Bot):
    def __init__(self, config, dyes_fr):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        dir = os.path.dirname(os.path.realpath(__file__))
        db_path = os.path.join(dir, config['database'])
        self.db_conn = sqlite3.connect(db_path)
        self.db_cursor = self.db_conn.cursor()
        self.db_conn.row_factory = sqlite3.Row
        self.create_tables()
        self.config = config

        self.dyes_fr = dyes_fr

        super().__init__(
            command_prefix=commands.when_mentioned_or(config['prefix']),
            intents=intents,
            help_command=None,
        )

    @tasks.loop(minutes=1.0)
    async def ping_task(self):
        # Fetch maps runs that have not been pinged yet
        bot.db_cursor.execute('SELECT * FROM maps_runs WHERE pinged=0')
        maps_runs = bot.db_cursor.fetchall()

        if not maps_runs:
            print('No maps to ping right now...')
            return

        current_time = datetime.now(timezone.utc)

        for maps_run in maps_runs:
            # Calculate time difference between current time and ping time
            current_time = datetime.now(timezone.utc)
            ping_time = datetime.fromtimestamp(maps_run[2], tz=timezone.utc) - timedelta(minutes=20)
            time_until_ping = (ping_time - current_time).total_seconds() / 60  # Convert to minutes

            # Debug message
            print(f"Time until ping for maps run {maps_run[0]}: {time_until_ping} minutes")

            if current_time >= ping_time:
                # Fetch the joined users
                joined_user_ids = maps_run[4].split(',')
                joined_users = [f"<@{user_id}>" for user_id in joined_user_ids if user_id]

                # Create an embed with the ping message
                embed = discord.Embed(
                    title="Maps Run Reminder",
                    description=f"The maps run will start in 20 minutes. Are you ready?\n\nJoined Users:\n" + "\n".join(joined_users),
                    color=0xff8a08
                )

                # Find the message to ping
                message_id = maps_run[0]
                channel_id = bot.config['events_channel_id']
                channel = bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.channel.send(f"<@&{bot.config['maps_notifications_role_id']}> ", embed=embed)

                        # Update the pinged status to true
                        bot.db_cursor.execute('UPDATE maps_runs SET pinged=1 WHERE message_id=?', (message_id,))
                        bot.db_conn.commit()

                    except discord.NotFound:
                        pass

    async def setup_hook(self):
        self.add_view(AdmissionMessage(timeout=None))
        print('Registered persistent view: AdmissionMessage')
        self.add_view(ApplicationMessage(timeout=None))
        print('Registered persistent view: ApplicationMessage')

        # Retrieve the message_id, discord_timestamp, and timestamp from the database
        self.db_cursor.execute('SELECT message_id, discord_timestamp, timestamp, available_slots FROM maps_runs')
        maps_runs = self.db_cursor.fetchall()

        # Recreate the MapsRunView instance for each message_id
        for message_id, discord_timestamp, timestamp, available_slots in maps_runs:
            view = MapsRunView(message_id=int(message_id), timestamp=discord_timestamp, available_slots=available_slots)
            self.add_view(view)
            print(f"Registered persistent view: MapsRunView (message_id={message_id})")

        return await super().setup_hook()

    async def on_ready(self):
        self.ping_task.start()
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print('------')

    def create_tables(self):
        self.db_cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER PRIMARY KEY,
            fc TEXT,
            ingame_name TEXT
        )
        ''')
        self.db_cursor.execute('''
        CREATE TABLE IF NOT EXISTS maps_runs (
            message_id INTEGER PRIMARY KEY,
            discord_timestamp TEXT,
            timestamp TIMESTAMP,
            available_slots INTEGER DEFAULT 8,
            user_ids TEXT,
            pinged INTEGER DEFAULT 0
        )
        ''')
        self.db_conn.commit()

# Load config from config.json file
def load_config():
    dir = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(dir, 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def load_dyes_fr():
    dir = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(dir, 'dyes_fr.json')
    with open(config_path, 'r') as f:
        return json.load(f)

bot = BotClient(load_config(), load_dyes_fr())

# UI Name modal
class ApplicationModal(discord.ui.Modal, title='Access application'):
    def __init__(self, fc: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fc = fc

    name = discord.ui.TextInput(
        label='What is your in-game name?',
        placeholder='Name LastName',
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not self.name.value or len(self.name.value.split(' ')) != 2:
            await interaction.response.send_message('Error: Invalid in-game name (format: Name LastName)', ephemeral=True)
            return

        bot.db_cursor.execute('INSERT INTO applications (user_id, fc, ingame_name) VALUES (?, ?, ?)', (interaction.user.id, self.fc, self.name.value))
        bot.db_conn.commit()

        application_channel = bot.get_channel(bot.config['admission_channel_id'])
        message_content = f"New application from {interaction.user.mention} (ID: {interaction.user.id}):\nIn-game name: {self.name.value}\nFC: {self.fc}"
        await application_channel.send(message_content, view=AdmissionMessage())
        await interaction.response.send_message(f"Application sent, awaiting approval...", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Oops! Something went wrong. Please try again', ephemeral=True)
        traceback.print_exception(type(error), error, error.__traceback__) # Make sure we know what the error actually is

# Approve/Deny view
class AdmissionMessage(discord.ui.View):
    async def interaction_check(self, interaction: discord.Interaction[discord.Client]) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        if member.guild_permissions.administrator and bot.config['administrator_role_id'] in [role.id for role in member.roles]:
            return True
        else:
            await interaction.response.send_message("You don't have permission to use this button.", ephemeral=True)
            return False

    def extract_user_id(self, message_content: str) -> int:
        start_index = message_content.find('(ID: ') + len('(ID: ')
        end_index = message_content.find(')', start_index)
        user_id_str = message_content[start_index:end_index]
        return int(user_id_str)

    @discord.ui.button(label='Approve', style=discord.ButtonStyle.green, custom_id='AdmissionMessage:approve_button')
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = self.extract_user_id(interaction.message.content)
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (user_id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_message('Error: user_id not found in applications database', ephemeral=True)
            return

        user = interaction.guild.get_member(user_id)

        if user:
            if application[1] == 'Seventh Haven':
                role = interaction.guild.get_role(bot.config['seventh_haven_role_id'])
            elif application[1] == 'Moon':
                role = interaction.guild.get_role(bot.config['moon_role_id'])
            elif application[1] == 'ONE':
                role = interaction.guild.get_role(bot.config['one_role_id'])
            newcomer_role = interaction.guild.get_role(bot.config['newcomer_role_id'])

            bot.db_cursor.execute('DELETE FROM applications WHERE user_id=?', (user_id,))
            bot.db_conn.commit()

            try:
                await user.remove_roles(newcomer_role)
                await user.add_roles(role)
                await user.edit(nick=application[2])
            except discord.errors.Forbidden:
                await bot.get_channel(bot.config['logs_channel_id']).send(f"Execution of application for {user.mention} failed, are you sure the user doesn\'t have a role above Moogly\'s role?")
            await interaction.message.delete()
            await interaction.response.send_message(f"Application for {user.mention} approved", ephemeral=True)
            await bot.get_channel(bot.config['logs_channel_id']).send(f"Application from {user.mention} (ID: {user_id}) approved:\nIn-game name: {application[2]}\nFC: {application[1]}")
            await user.send('Your application to get access to Seventh Haven server has been approved, you now have access to the server.')
        else:
            await interaction.response.send_message('Error: Failed to fetch user', ephemeral=True)

    @discord.ui.button(label='Decline', style=discord.ButtonStyle.red, custom_id='AdmissionMessage:decline_button')
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = self.extract_user_id(interaction.message.content)
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (user_id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_message('Error: user_id not found in applications database', ephemeral=True)
            return

        user = bot.get_user(user_id)

        if user:
            bot.db_cursor.execute('DELETE FROM applications WHERE user_id=?', (user_id,))
            bot.db_conn.commit()

            await interaction.response.send_message(f"Application for {user.mention} declined", ephemeral=True)
            await bot.get_channel(bot.config['logs_channel_id']).send(f"Application from {user.mention} (ID: {user_id}) declined:\nIn-game name: {application[2]}\nFC: {application[1]}")
            await user.send('Your application to get access to Seventh Haven server has been declined, please try again.')
            await interaction.message.delete()
        else:
            await interaction.response.send_message('Error: Failed to fetch user', ephemeral=True)

# Send application view
class ApplicationMessage(discord.ui.View):
    async def interaction_check(self, interaction: discord.Interaction[discord.Client]) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        if bot.config['newcomer_role_id'] in [role.id for role in member.roles]:
            return True
        else:
            await interaction.response.send_message("You don't have permission to use this button. Please contact an administrator.", ephemeral=True)
            return False

    @discord.ui.button(label='Seventh Haven', style=discord.ButtonStyle.blurple, custom_id='ApplicationMessage:seventh_haven_button', emoji=discord.PartialEmoji.from_str('<:seventhhaven:1241086148844064819>'))
    async def seventh_haven_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (interaction.user.id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_modal(ApplicationModal('Seventh Haven'))
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

    @discord.ui.button(label='Moon', style=discord.ButtonStyle.green, custom_id='ApplicationMessage:moon_button', emoji=discord.PartialEmoji.from_str('<:moon:1241086139558002738>'))
    async def moon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (interaction.user.id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_modal(ApplicationModal('Moon'))
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)
    
    @discord.ui.button(label='ONE', style=discord.ButtonStyle.red, custom_id='ApplicationMessage:one_button', emoji=discord.PartialEmoji.from_str('<:one:1241086126140166164>'))
    async def one_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (interaction.user.id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_modal(ApplicationModal('ONE'))
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

# Add application form to current channel | !application_form
@bot.command()
@commands.has_permissions(administrator=True)
@commands.has_role(bot.config['administrator_role_id'])
async def application_form(interaction: discord.Interaction):
    await interaction.channel.send('Which FC are you member of?', view=ApplicationMessage())

# Clear all applications | !application_clear
@bot.command()
@commands.has_permissions(administrator=True)
@commands.has_role(bot.config['administrator_role_id'])
async def application_clear(interaction: discord.Interaction):
    bot.db_cursor.execute('DELETE FROM applications')
    bot.db_conn.commit()
    await interaction.channel.send('All applications cleared.')

# Delete a specific application | !application_delete <mention>
@bot.command()
@commands.has_permissions(administrator=True)
@commands.has_role(bot.config['administrator_role_id'])
async def application_delete(interaction: discord.Interaction, user: discord.User):
    if not isinstance(user, discord.User):
        await interaction.response.send_message('Error: invalid user argument, format: !application_delete <mention>')
        return
    bot.db_cursor.execute('DELETE FROM applications WHERE user_id=?', (user.id,))
    bot.db_conn.commit()
    await interaction.channel.send(f"Application deleted for user {user.mention}.")

# List guild's emojis ids
@commands.has_permissions(administrator=True)
@commands.has_role(bot.config['administrator_role_id'])
@bot.command()
async def get_guild_emojis(interaction: discord.Interaction):
    emojis = [f"{emoji} | {emoji.name} | {emoji.id}" for emoji in interaction.guild.emojis]
    if emojis:
        await interaction.channel.send("\n".join(emojis))
    else:
        await interaction.channel.send("No emojis found in this server.")

# Translate english dyes in french using | as a separator
@bot.command()
async def translate_dyes_fr(interaction: discord.Interaction, *args):
    # Split the input arguments
    arguments = ''.join(args)
    dyes = arguments.split('|')
    
    # Count occurrences of each translated dye name
    dye_counts = {}
    for dye_name in dyes:
        for dye_entry in bot.dyes_fr:
            if dye_entry["original_name"].replace(" ", "") == dye_name.strip():
                translated_name = dye_entry["translated_name"]
                dye_counts[translated_name] = dye_counts.get(translated_name, 0) + 1
                break
    
    # Create an embed to display the results
    embed = discord.Embed(
        title="Translated dyes (french)",
        color=0x5d3fd3
    )
    for translated_name, count in dye_counts.items():
        original_name = [entry["original_name"] for entry in bot.dyes_fr if entry["translated_name"] == translated_name][0]
        embed.add_field(name=f"{count}x {translated_name}", value=f"({original_name})", inline=False)

    await interaction.channel.send(embed=embed)

class MapsRunView(discord.ui.View):
    def __init__(self, message_id, timestamp, available_slots):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.timestamp = timestamp
        self.available_slots = available_slots
        self.embed = discord.Embed()
        self.update_embed()

    def update_embed(self):
        # Fetch joined users
        bot.db_cursor.execute('SELECT user_ids FROM maps_runs WHERE message_id=?', (self.message_id,))
        maps_run = bot.db_cursor.fetchone()
    
        if maps_run and maps_run[0]:
            joined_user_ids = maps_run[0].split(',')
            joined_users = [f"<@{user_id}>" for user_id in joined_user_ids if user_id]
            joined_users_description = "\n\n**Joined users**:\n" + "\n".join(joined_users)
        else:
            joined_users_description = ""

        self.embed = discord.Embed(
            title="Next maps run",
            description=f"Next maps run on {self.timestamp}\nWho's in? 💰\nCurrently available slots: {self.available_slots} / 8{joined_users_description}",
            color=0xffc100
        )

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, custom_id="join_map_run")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        bot.db_cursor.execute('SELECT * FROM maps_runs WHERE message_id=?', (self.message_id,))
        maps_run = bot.db_cursor.fetchone()

        if maps_run:
            user_ids = maps_run[4].split(',')
            if str(user_id) not in user_ids:
                if self.available_slots > 0:
                    if maps_run[5] == 0: # Check if ping was already sent, meaning that the map will be running soon
                        user_ids.append(str(user_id))
                        self.available_slots -= 1
                        bot.db_cursor.execute(
                            'UPDATE maps_runs SET user_ids=?, available_slots=? WHERE message_id=?',
                            (','.join(user_ids), self.available_slots, self.message_id)
                        )
                        bot.db_conn.commit()

                        self.update_embed()
                        await interaction.message.edit(embed=self.embed, view=self)
                        await interaction.response.send_message('You have successfully joined the map run! You will be pinged 20 minutes before the maps run starts.', ephemeral=True)
                    else:
                        await interaction.response.send_message('The map run is starting soon. You cannot join now.', ephemeral=True)
                else:
                    await interaction.response.send_message('Sorry, no more available slots for this map run.', ephemeral=True)
            else:
                await interaction.response.send_message('You have already joined this map run.', ephemeral=True)

# Create a new map run message | !maps_create <timestamp>
@bot.command()
@commands.has_permissions(administrator=True)
@commands.has_role(bot.config['administrator_role_id'])
async def maps_create(interaction: discord.Interaction, timestamp: str):
    channel = bot.get_channel(bot.config['events_channel_id'])

    # Check if the timestamp is valid
    try:
        timestamp_dt = datetime.fromtimestamp(int(timestamp.split(':')[1].split(':')[0]), tz=timezone.utc)
    except ValueError:
        await interaction.channel.send('Invalid timestamp format. Please use the correct Discord timestamp format.')
        return

    view = MapsRunView(message_id=None, timestamp=timestamp, available_slots=8)
    message = await channel.send(f"<@&{bot.config['maps_notifications_role_id']}>", embed=view.embed, view=view)

    # Update the message_id in the view
    view.message_id = message.id

    # Store the message info in the database
    bot.db_cursor.execute(
        'INSERT INTO maps_runs (message_id, discord_timestamp, timestamp, available_slots, user_ids, pinged) VALUES (?, ?, ?, ?, ?, ?)',
        (int(message.id), timestamp, timestamp_dt.timestamp(), 8, '', 0)
    )
    bot.db_conn.commit()

    # Update the embed with the joined users
    view.update_embed()
    await message.edit(embed=view.embed, view=view)

# Outputs a list of users who have joined the map run | !maps_list <timestamp>
@bot.command()
@commands.has_permissions(administrator=True)
@commands.has_role(bot.config['administrator_role_id'])
async def maps_list(interaction: discord.Interaction, message_id: int):
    # Fetch the message
    channel = bot.get_channel(bot.config['events_channel_id'])
    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        await interaction.channel.send('Message not found.')
        return

    # Check if the message is a map run message
    bot.db_cursor.execute('SELECT * FROM maps_runs WHERE message_id=?', (message_id,))
    maps_run = bot.db_cursor.fetchone()
    if not maps_run:
        await interaction.channel.send('Message is not a maps run message.')
        return

    # Fetch joined users
    joined_user_ids = maps_run[4].split(',')
    joined_users = [interaction.guild.get_member(int(user_id)).mention for user_id in joined_user_ids if user_id]

    # Create an embed with the joined users
    embed = discord.Embed(
        title="Joined Users",
        description="\n".join(joined_users) if joined_users else "No users have joined yet.",
        color=0x5d3fd3
    )

    await interaction.channel.send(embed=embed)

# Run the bot
bot.run(bot.config['token'])