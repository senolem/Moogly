import discord
from discord.ext import commands
import json
import sqlite3
import traceback

class BotClient(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(config["prefix"]),
            intents=intents,
            help_command=None,
        )

        # Connect to SQLite database
        self.db_conn = sqlite3.connect(config["prefix"])
        self.db_cursor = self.db_conn.cursor()

        # Initialize database tables if not exist
        self.create_tables()

        self.config = config

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    def create_tables(self):
        # Create the application_data table if it doesn't exist
        self.db_cursor.execute("""
        CREATE TABLE IF NOT EXISTS application_data (
            user_id INTEGER PRIMARY KEY,
            fc TEXT,
            ingame_name TEXT
        )
        """)
        self.db_conn.commit()

# UI Name modal
class ApplicationModal(discord.ui.Modal, title='Access application'):
    name = discord.ui.TextInput(
        label='What is your in-game name?',
        placeholder='Name LastName',
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not self.name.value or len(self.name.value.split(' ')) != 2:
            await interaction.response.send_message('Error: Invalid in-game name (format: Name LastName)', ephemeral=True)
            return

        bot.db_cursor.execute("SELECT * FROM application_data WHERE user_id=?", (interaction.user.id,))
        existing_data = bot.db_cursor.fetchone()
        if existing_data:
            bot.db_cursor.execute("UPDATE application_data SET ingame_name=? WHERE user_id=?", (self.name.value, interaction.user.id))
        else:
            bot.db_cursor.execute("INSERT INTO application_data (user_id, ingame_name) VALUES (?, ?)", (interaction.user.id, self.name.value))
        bot.db_conn.commit()

        application_channel = bot.get_channel(bot.config["admission_channel_id"])
        message_content = f'New application from {interaction.user.mention} (ID: {interaction.user.id}):\nIn-game name: {self.name.value}\nFC: {existing_data["fc"]}'
        await application_channel.send(message_content, view=AdmissionMessage())
        await interaction.response.send_message(f'Application sent, awaiting approval...', ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Oops! Something went wrong. Please try again', ephemeral=True)
        traceback.print_exception(type(error), error, error.__traceback__) # Make sure we know what the error actually is

# Approve/Deny view
class AdmissionMessage(discord.ui.View):
    def extract_user_id(self, message_content: str) -> int:
        start_index = message_content.find("(ID: ") + len("(ID: ")
        end_index = message_content.find(")", start_index)
        user_id_str = message_content[start_index:end_index]
        return int(user_id_str)

    @discord.ui.button(label='Approve', style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = self.extract_user_id(interaction.message.content)
        bot.db_cursor.execute("SELECT * FROM application_data WHERE user_id=?", (user_id,))
        application_data = bot.db_cursor.fetchone()

        if not application_data:
            await interaction.response.send_message('Error: user_id not found in applications list!', ephemeral=True)
            return

        user = interaction.guild.get_member(user_id)

        if user:
            if application_data['fc'] == 'Seventh Haven':
                role = interaction.guild.get_role(bot.config["seventh_haven_role_id"])
            elif application_data['fc'] == 'Moon':
                role = interaction.guild.get_role(bot.config["moon_role_id"])

            bot.db_cursor.execute("DELETE FROM application_data WHERE user_id=?", (user_id,))
            bot.db_conn.commit()

            await user.add_roles(role)
            await user.edit(nick=application_data['ingame_name'])
            await interaction.message.delete()
            await interaction.response.send_message(f'Application for {user.mention} approved!', ephemeral=True)
            await user.send('Your application to get access to Seventh Haven server has been approved, you now have access to the server.')
        else:
            await interaction.response.send_message('Error: Failed to fetch user', ephemeral=True)

    @discord.ui.button(label='Decline', style=discord.ButtonStyle.red)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = self.extract_user_id(interaction.message.content)
        bot.db_cursor.execute("SELECT * FROM application_data WHERE user_id=?", (user_id,))
        application_data = bot.db_cursor.fetchone()

        if not application_data:
            await interaction.response.send_message('Error: user_id not found in applications list!', ephemeral=True)
            return

        user = bot.get_user(user_id)

        if user:
            bot.db_cursor.execute("DELETE FROM application_data WHERE user_id=?", (user_id,))
            bot.db_conn.commit()

            await interaction.response.send_message(f'Application for {user.mention} declined!', ephemeral=True)
            await user.send('Your application to get access to Seventh Haven server has been declined, please try again.')
            await interaction.message.delete()
        else:
            await interaction.response.send_message('Error: Failed to fetch user', ephemeral=True)

# Send application view
class ApplicationMessage(discord.ui.View):
    @discord.ui.button(label='Seventh Haven', style=discord.ButtonStyle.blurple)
    async def seventh_haven_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute("SELECT * FROM application_data WHERE user_id=?", (interaction.user.id,))
        existing_data = bot.db_cursor.fetchone()

        if not existing_data:
            bot.db_cursor.execute("INSERT INTO application_data (user_id, fc) VALUES (?, ?)", (interaction.user.id, "Seventh Haven"))
            bot.db_conn.commit()
            await interaction.response.send_modal(ApplicationModal())
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

    @discord.ui.button(label='Moon', style=discord.ButtonStyle.green)
    async def moon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute("SELECT * FROM application_data WHERE user_id=?", interaction.user.id)
        existing_data = bot.db_cursor.fetchone()

        if not existing_data:
            bot.db_cursor.execute("INSERT INTO application_data (user_id, fc) VALUES (?, ?)", (interaction.user.id, "Moon"))
            bot.db_conn.commit()
            await interaction.response.send_modal(ApplicationModal())
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

bot = BotClient(load_config())

# Add application form to current channel | !application_form
@bot.command()
async def application_form(interaction: discord.Interaction):
    await interaction.channel.send('Which FC are you member of?', view=ApplicationMessage())

# Clear all applications | !application_clear
@bot.command()
async def application_clear(interaction: discord.Interaction):
    bot.db_cursor.execute("DELETE FROM application_data")
    bot.db_conn.commit()
    await interaction.channel.send('All applications cleared.')

# Delete a specific application | !application_delete <mention>
@bot.command()
async def application_delete(interaction: discord.Interaction, user: discord.User):
    if not isinstance(user, discord.User):
        await interaction.response.send_message('Error: invalid user argument, format: !application_delete <mention>')
        return
    bot.db_cursor.execute("DELETE FROM application_data WHERE user_id=?", (user.id,))
    bot.db_conn.commit()
    await interaction.channel.send(f'Application deleted for user {user.mention}.')

# Run the bot
bot.run(bot.config["token"])