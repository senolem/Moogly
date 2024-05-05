import discord
from discord.ext import commands
import json
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

        # Data
        self.application_data = {}
        self.config = config

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    async def setup_hook(self) -> None:
        await self.tree.sync(guild=self.get_guild(self.config["guild_id"]))

class ApplicationModal(discord.ui.Modal, title='Access application'):
    name = discord.ui.TextInput(
        label='What is your in-game name?',
        placeholder='Name LastName',
    )

    async def on_submit(self, interaction: discord.Interaction):
        application_data = bot.application_data.get(interaction.user.id)
        if application_data:
            application_data['ingame_name'] = self.name.value
            application_channel = bot.get_channel(bot.config["admission_channel_id"])
            message_content = f'New application from {interaction.user.mention} (ID: {interaction.user.id}):\nIn-game name: {self.name.value}\nFC: {application_data["fc"]}'
            await application_channel.send(message_content, view=AdmissionMessage())
            await interaction.response.send_message(f'Application sent, awaiting approval...', ephemeral=True)
        else:
            await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)
        traceback.print_exception(type(error), error, error.__traceback__) # Make sure we know what the error actually is

class AdmissionMessage(discord.ui.View):
    def extract_user_id(self, message_content: str) -> int:
        start_index = message_content.find("(ID: ") + len("(ID: ")
        end_index = message_content.find(")", start_index)
        user_id_str = message_content[start_index:end_index]
        return int(user_id_str)

    @discord.ui.button(label='Approve', style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = self.extract_user_id(interaction.message.content)
        if user_id not in bot.application_data:
            await interaction.response.send_message('Error: user_id not found in applications list!', ephemeral=True)
        else:
            application_data = bot.application_data.get(user_id)
            user = interaction.guild.get_member(user_id)

            if user:
                if application_data['fc'] == 'Seventh Haven':
                    role = interaction.guild.get_role(bot.config["seventh_haven_role_id"])
                elif application_data['fc'] == 'Moon':
                    role = interaction.guild.get_role(bot.config["moon_role_id"])
                bot.application_data.pop(user_id)
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
        user = bot.get_user(user_id)

        if user:
            bot.application_data.pop(user_id)
            await interaction.response.send_message(f'Application for {user.mention} declined!', ephemeral=True)
            await user.send('Your application to get access to Seventh Haven server has been declined, please try again.')
            await interaction.message.delete()
        else:
            await interaction.response.send_message('Error: Failed to fetch user', ephemeral=True)

class ApplicationMessage(discord.ui.View):
    @discord.ui.button(label='Seventh Haven', style=discord.ButtonStyle.blurple)
    async def seventh_haven_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.id in bot.application_data:
            bot.application_data[interaction.user.id] = {"fc": "Seventh Haven"}
            await interaction.response.send_modal(ApplicationModal())
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

    @discord.ui.button(label='Moon', style=discord.ButtonStyle.green)
    async def moon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.id in bot.application_data:
            bot.application_data[interaction.user.id] = {"fc": "Moon"}
            await interaction.response.send_modal(ApplicationModal())
        else:
            await interaction.response.send_message('You already sent an application, please wait until an administrator reviews it.', ephemeral=True)

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

bot = BotClient(load_config())

@bot.command()
async def application_form_message(interaction: discord.Interaction):
    await interaction.channel.send('Which FC are you member of?', view=ApplicationMessage())

# Run the bot
bot.run(bot.config["token"])
