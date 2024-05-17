import discord
from discord.ext import commands
import json
import sqlite3
import traceback
import os

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
        
    async def setup_hook(self):
        self.add_view(AdmissionMessage(timeout=None))
        print('Registered persistent view: AdmissionMessage')
        self.add_view(ApplicationMessage(timeout=None))
        print('Registered persistent view: ApplicationMessage')
        return await super().setup_hook()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    def create_tables(self):
        self.db_cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER PRIMARY KEY,
            fc TEXT,
            ingame_name TEXT
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
        message_content = f'New application from {interaction.user.mention} (ID: {interaction.user.id}):\nIn-game name: {self.name.value}\nFC: {self.fc}'
        await application_channel.send(message_content, view=AdmissionMessage())
        await interaction.response.send_message(f'Application sent, awaiting approval...', ephemeral=True)

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
                await bot.get_channel(bot.config['logs_channel_id']).send(f'Execution of application for {user.mention} failed, are you sure the user doesn\'t have a role above Moogly\'s role?')
            await interaction.message.delete()
            await interaction.response.send_message(f'Application for {user.mention} approved', ephemeral=True)
            await bot.get_channel(bot.config['logs_channel_id']).send(f'Application from {user.mention} (ID: {user_id}) approved:\nIn-game name: {application[2]}\nFC: {application[1]}')
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

            await interaction.response.send_message(f'Application for {user.mention} declined', ephemeral=True)
            await bot.get_channel(bot.config['logs_channel_id']).send(f'Application from {user.mention} (ID: {user_id}) declined:\nIn-game name: {application[2]}\nFC: {application[1]}')
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

    @discord.ui.button(label='Seventh Haven', style=discord.ButtonStyle.blurple, custom_id='ApplicationMessage:seventh_haven_button', emoji='<:dove:>')
    async def seventh_haven_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (interaction.user.id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_modal(ApplicationModal('Seventh Haven'))
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

    @discord.ui.button(label='Moon', style=discord.ButtonStyle.green, custom_id='ApplicationMessage:moon_button', emoji='<:moon:>')
    async def moon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.db_cursor.execute('SELECT * FROM applications WHERE user_id=?', (interaction.user.id,))
        application = bot.db_cursor.fetchone()

        if not application:
            await interaction.response.send_modal(ApplicationModal('Moon'))
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)
    
    @discord.ui.button(label='ONE', style=discord.ButtonStyle.red, custom_id='ApplicationMessage:one_button', emoji='<:one:>')
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
    await interaction.channel.send(f'Application deleted for user {user.mention}.')

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
    embed = discord.Embed(title="Translated dyes (french)", color=0x00ff00)
    for translated_name, count in dye_counts.items():
        original_name = [entry["original_name"] for entry in bot.dyes_fr if entry["translated_name"] == translated_name][0]
        embed.add_field(name=f"{count}x {translated_name}", value=f"({original_name})", inline=False)

    await interaction.channel.send(embed=embed)

# Run the bot
bot.run(bot.config['token'])