import discord
import aiosqlite
import hashlib
import os

# Configuration for channel and role IDs
CHANNELS = {
    "verification": 1287851473551495259,  # Channel ID for verification notifications
    "log": 1290308826020712500  # Log channel ID for actions
}

ROLES = {
    "verified": 1289720252048867338,  # Role ID to assign after verification
    "admin": 1289730759086837882  # Role ID for admins who can approve/reject
}

FILES_DIR = "files"

# Ensure the directory exists for saving files
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# Database initialization
async def create_db():
    async with aiosqlite.connect('verifications.db') as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS verifications (
            user_id INTEGER PRIMARY KEY,
            age TEXT,
            furry_intro TEXT,
            server_visited TEXT,
            goal TEXT,
            source TEXT,
            status TEXT DEFAULT 'pending'
        )
        """)
        await db.commit()

# Initialize the bot with all intents
bot = discord.Bot(intents=discord.Intents.all())

# Helper function to generate file hash
def get_file_hash(file_content):
    return hashlib.sha256(file_content).hexdigest()

# Check if the file is already saved
def check_for_duplicate_file(file_hash):
    return os.path.exists(os.path.join(FILES_DIR, file_hash))

# Save file to the directory
def save_file(file_content, file_hash):
    with open(os.path.join(FILES_DIR, file_hash), "wb") as f:
        f.write(file_content)

# Event listener for messages to handle file attachments
@bot.event
async def on_message(message):
    if message.attachments:
        for attachment in message.attachments:
            file_content = await attachment.read()
            file_hash = get_file_hash(file_content)

            if check_for_duplicate_file(file_hash):
                await message.delete()
                print("Duplicate video deleted!")
            else:
                save_file(file_content, file_hash)

# Custom view with a persistent verification button
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Start Verification", style=discord.ButtonStyle.green, custom_id="persistent_button")
    async def button_callback(self, button, interaction):
        user_id = interaction.user.id

        async with aiosqlite.connect('verifications.db') as db:
            cursor = await db.execute("SELECT * FROM verifications WHERE user_id = ? AND status = 'pending'", (user_id,))
            result = await cursor.fetchone()

        if result is not None:
            await interaction.response.send_message("You have already submitted a form.", ephemeral=True)
        else:
            await interaction.response.send_modal(MyModal())

# Modal for verification form
class MyModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Verification Form")

        self.add_item(discord.ui.InputText(label="Your age", max_length=2, min_length=2))
        self.add_item(discord.ui.InputText(label="How did you learn about furries?", max_length=512))
        self.add_item(discord.ui.InputText(label="Tell us about yourself", max_length=512, placeholder="Hobbies, interests, dreams", style=discord.InputTextStyle.multiline))
        self.add_item(discord.ui.InputText(label="Goal in joining the server", max_length=512))
        self.add_item(discord.ui.InputText(label="How did you hear about the server?", max_length=512, placeholder="Friend, website, etc."))

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        
        # Check for special characters in the input
        for child in self.children[1:5]:
            if any(char in child.value for char in ['﷽', '𒐫', '⸻', '꧅']):
                await interaction.response.send_message("Form incorrectly filled.", ephemeral=True)
                return
        
        if not self.children[0].value.isdigit():
            await interaction.response.send_message("Age must contain only numbers.", ephemeral=True)
            return

        # Create embed with form details
        embed = discord.Embed(
            title="New Form Submission!",
            description=f"""Basic Information:
            **Username:** <@{interaction.user.id}> | {interaction.user.name}#{interaction.user.discriminator}
            **Account Created:** <t:{int(interaction.user.created_at.timestamp())}:R> (<t:{int(interaction.user.created_at.timestamp())}:d>)
            **Joined Server:** <t:{int(interaction.user.joined_at.timestamp())}:R> (<t:{int(interaction.user.joined_at.timestamp())}:d>)
            """,
            color=discord.Colour.blurple(),
        )
        embed.add_field(name="Your Age", value=self.children[0].value)
        embed.add_field(name="How did you learn about furries?", value=self.children[1].value)
        embed.add_field(name="Tell us about yourself", value=self.children[2].value)
        embed.add_field(name="Goal in joining the server", value=self.children[3].value)
        embed.add_field(name="How did you hear about the server?", value=self.children[4].value)
        embed.set_footer(text=f"ID: {interaction.user.id}")
        
        channel = bot.get_channel(CHANNELS['verification'])
        await channel.send(content=f"<@&{ROLES['admin']}>", embeds=[embed], view=ActionButtons(user_id=interaction.user.id))
        
        async with aiosqlite.connect('verifications.db') as db:
            await db.execute("""
                INSERT OR REPLACE INTO verifications (user_id, age, furry_intro, server_visited, goal, source, status) 
                VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                (user_id, self.children[0].value, self.children[1].value, self.children[2].value, self.children[3].value, self.children[4].value))
            await db.commit()

        await interaction.response.send_message("Form successfully submitted.", ephemeral=True)

# Buttons for admins to accept/reject forms
class ActionButtons(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Check if user has the admin role
        if ROLES['admin'] not in [role.id for role in interaction.user.roles]:
            await interaction.followup.send("You don't have permission.", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        verified_role = guild.get_role(ROLES['verified'])
        await member.add_roles(verified_role)

        log_channel = bot.get_channel(CHANNELS['log'])
        embed = discord.Embed(
            title="Form Accepted",
            description=f"**User:** <@{self.user_id}> has been verified.",
            color=discord.Colour.green(),
        )
        embed.add_field(name="Accepted by:", value=f"<@{interaction.user.id}>")
        await log_channel.send(embed=embed)

        async with aiosqlite.connect('verifications.db') as db:
            await db.execute("UPDATE verifications SET status = ? WHERE user_id = ?", ('accepted', self.user_id))
            await db.commit()

        try:
            await member.send("Your form has been accepted! Welcome to the server!")
        except discord.Forbidden:
            await interaction.channel.send(f"Could not send a DM to <@{self.user_id}>.", ephemeral=True)
        
        await interaction.message.delete()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if ROLES['admin'] not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have permission.", ephemeral=True)
            return
        
        await interaction.response.send_modal(RejectModal(self.user_id))

class RejectModal(discord.ui.Modal):
    def __init__(self, user_id: int):
        super().__init__(title="Form Rejection")
        self.user_id = user_id
        self.add_item(discord.ui.InputText(label="Reason for rejection", max_length=1024))

    async def callback(self, interaction: discord.Interaction):
        reason = self.children[0].value
        log_channel = bot.get_channel(CHANNELS['log'])
        embed = discord.Embed(
            title="Form Rejected",
            description=f"**User:** <@{self.user_id}> form was rejected.",
            color=discord.Colour.red(),
        )
        embed.add_field(name="Reason:", value=reason)
        embed.add_field(name="Rejected by:", value=f"<@{interaction.user.id}>")
        await log_channel.send(embed=embed)

        async with aiosqlite.connect('verifications.db') as db:
            await db.execute("UPDATE verifications SET status = ? WHERE user_id = ?", ('rejected', self.user_id))
            await db.commit()

        guild = interaction.guild
        member = guild.get_member(self.user_id)
        try:
            await member.send(f"Your form has been rejected. Reason: {reason}")
        except discord.Forbidden:
            await interaction.channel.send(f"Could not send a DM to <@{self.user_id}>.", ephemeral=True)

        await interaction.message.delete()

        await interaction.response.send_message(f"Form rejected. Reason: {reason}", ephemeral=True)

# Bot on_ready event to set up the database and persistent views
@bot.event
async def on_ready():
    await create_db()
    bot.add_view(MyView())
    print(f"Logged in as {bot.user}")

# Slash command to send the verification message with a selectable channel option
@bot.slash_command(guild_ids=[1265987613303509024])
@discord.default_permissions(administrator=True)
async def send_verify_message(
    ctx: discord.ApplicationContext,
    channel: discord.Option(
        discord.TextChannel,
        description="Select the channel to send the verification message",
        required=True
    )
):
    """
    Command to send a verification message to the selected text channel.
    """
    # Creating the embed for the verification message
    embed = discord.Embed(
        title="FURRIFICATION",
        description="""**~ Hello, furry!** :sparkles:
        Please fill out the short form below and be patient while it is reviewed. 
        We will message you when your form is accepted or rejected.""",
        color=discord.Colour.blurple(),
    )
    
    # Sending the message to the selected channel
    await channel.send("@everyone", embed=embed, view=MyView())
    
    # Confirmation to the admin
    await ctx.respond(f"Verification message sent to {channel.mention}!", ephemeral=True)

# Run the bot with the token
bot.run("TOKENHERE")
