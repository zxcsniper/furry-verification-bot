import discord
import aiosqlite
import hashlib
import os

FILES_DIR = "files"

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

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

bot = discord.Bot(intents=discord.Intents.all())

def get_file_hash(file_content):
    return hashlib.sha256(file_content).hexdigest()

def check_for_duplicate_file(file_hash):
    return os.path.exists(os.path.join(FILES_DIR, file_hash))

def save_file(file_content, file_hash):
    with open(os.path.join(FILES_DIR, file_hash), "wb") as f:
        f.write(file_content)

@bot.event
async def on_message(message):
    if message.attachments:
        for attachment in message.attachments:
            file_content = await attachment.read()
            file_hash = get_file_hash(file_content)

            if check_for_duplicate_file(file_hash):
                await message.delete()
                print("Video Deleted!")
            else:
                save_file(file_content, file_hash)

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
            await interaction.response.send_message("You have already submitted a form and cannot do it again.", ephemeral=True)
        else:
            await interaction.response.send_modal(MyModal())

class MyModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Verification")

        self.add_item(discord.ui.InputText(label="Your age", max_length=2, min_length=2))
        self.add_item(discord.ui.InputText(label="How did you learn about furries?", max_length=512))
        self.add_item(discord.ui.InputText(label="Tell us about yourself", max_length=512, placeholder="Hobbies, interests, books, movies, facts, dreams, plans", style=discord.InputTextStyle.multiline))
        self.add_item(discord.ui.InputText(label="What is your goal in joining the server?", max_length=512))
        self.add_item(discord.ui.InputText(label="How did you learn about the server?", max_length=512, placeholder="Mention a friend or site. If it’s a partnership, where from?"))
        
    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        
        for child in self.children[1:5]:
            if any(char in child.value for char in ['﷽', '𒐫', '⸻', '꧅']):
                await interaction.response.send_message("The form is incorrectly filled out.", ephemeral=True)
                return
        
        if not self.children[0].value.isdigit():
            await interaction.response.send_message("Your age must contain only numbers.", ephemeral=True)
            return

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
        embed.add_field(name="Tell us a little about yourself", value=self.children[2].value)
        embed.add_field(name="Goal in joining the server", value=self.children[3].value)
        embed.add_field(name="How did you learn about the server?", value=self.children[4].value)
        embed.set_footer(text=f"ID: {interaction.user.id}")
        
        channel_id = 1287851473551495259
        channel = bot.get_channel(channel_id)
        await channel.send(content="<@&1289730759086837882>", embeds=[embed], view=ActionButtons(user_id=interaction.user.id))  # Send the embed with action buttons
        async with aiosqlite.connect('verifications.db') as db:
            await db.execute("INSERT OR REPLACE INTO verifications (user_id, age, furry_intro, server_visited, goal, source, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')", 
                             (user_id, self.children[0].value, self.children[1].value, self.children[2].value, self.children[3].value, self.children[4].value))
            await db.commit()
        await interaction.response.send_message("Your form has been successfully submitted for verification.", ephemeral=True)

class ActionButtons(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if 1289730759086837882 not in [role.id for role in interaction.user.roles]:
            await interaction.followup.send("You do not have permission to do this.", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        verified_role = guild.get_role(1289720252048867338)
        await member.add_roles(verified_role)
        
        log_channel = bot.get_channel(1290308826020712500)
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
        if 1289730759086837882 not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You do not have permission to do this.", ephemeral=True)
            return
        
        await interaction.response.send_modal(RejectModal(self.user_id))

class RejectModal(discord.ui.Modal):
    def __init__(self, user_id: int):
        super().__init__(title="Form Rejection")
        self.user_id = user_id
        self.add_item(discord.ui.InputText(label="Reason for rejection", max_length=1024))

    async def callback(self, interaction: discord.Interaction):
        reason = self.children[0].value
        log_channel = bot.get_channel(1290308826020712500)
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

@bot.event
async def on_ready():
    await create_db()
    bot.add_view(MyView())
    print(f"We have logged in as {bot.user}")

@bot.slash_command(guild_ids=[1265987613303509024])
@discord.default_permissions(administrator=True)
async def send_verify_message(ctx):
    channel_id = 1289730461945561180
    channel = bot.get_channel(channel_id)
    if channel is not None:
        embed = discord.Embed(
            title="FURRIFICATION",
            description="""**~ Hello, furry!** :sparkles:
Please fill out the short form below and be patient while it is reviewed. It might take a little while. We will message you when your form is accepted or, if something goes wrong, rejected.""",
            color=discord.Colour.blurple(),
        )
        await channel.send("@everyone", embed=embed, view=MyView())
        await ctx.response.send_message("Message sent!", ephemeral=True)

bot.run("Token here")
