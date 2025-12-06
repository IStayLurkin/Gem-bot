import discord
from discord.ui import Button, View

class ToolView(View):
    def __init__(self, last_prompt: str, channel_id: int, user_id: int):
        super().__init__(timeout=180)
        self.last_prompt = last_prompt
        self.channel_id = channel_id
        self.user_id = user_id
        self.add_item(Button(label="Search Web", style=discord.ButtonStyle.secondary, custom_id="tool_search", emoji="🔍"))
        self.add_item(Button(label="Re-Image", style=discord.ButtonStyle.secondary, custom_id="tool_reimage", emoji="🖼️"))
        self.add_item(Button(label="Summarize", style=discord.ButtonStyle.secondary, custom_id="tool_summarize", emoji="📄"))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Search Web", style=discord.ButtonStyle.secondary, custom_id="tool_search", emoji="🔍", row=0)
    async def search_button(self, interaction: discord.Interaction, button: Button):
        await interaction.followup.send(f"Simulating command: search_web", ephemeral=True)
        channel = interaction.client.get_channel(self.channel_id)
        if channel:
            await channel.send(f"!TOOL_REQUEST search_web \"{self.last_prompt}\" {self.user_id}")

    @discord.ui.button(label="Re-Image", style=discord.ButtonStyle.secondary, custom_id="tool_reimage", emoji="🖼️", row=0)
    async def reimage_button(self, interaction: discord.Interaction, button: Button):
        await interaction.followup.send(f"Simulating command: generate_image", ephemeral=True)
        channel = interaction.client.get_channel(self.channel_id)
        if channel:
            await channel.send(f"!TOOL_REQUEST generate_image \"{self.last_prompt}\" {self.user_id}")
             
    @discord.ui.button(label="Summarize", style=discord.ButtonStyle.secondary, custom_id="tool_summarize", emoji="📄", row=0)
    async def summarize_button(self, interaction: discord.Interaction, button: Button):
        await interaction.followup.send(f"Simulating command: summarize_last_message", ephemeral=True)
        channel = interaction.client.get_channel(self.channel_id)
        if channel:
            await channel.send(f"!TOOL_REQUEST summarize_last_message \"{self.last_prompt}\" {self.user_id}")

