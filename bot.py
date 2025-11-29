import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
from datetime import datetime
import pytz
import chat_exporter
import io
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)
def init_db():
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS exchangers
                 (user_id INTEGER PRIMARY KEY, security_holding REAL, exchanger_type TEXT, joined_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rates
                 (type TEXT PRIMARY KEY, rate REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  exchanger_id INTEGER, 
                  client_id INTEGER, 
                  exchange_type TEXT, 
                  amount_usd REAL, 
                  crypto TEXT,
                  date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS active_tickets
                 (channel_id INTEGER PRIMARY KEY,
                  client_id INTEGER,
                  exchanger_id INTEGER,
                  exchange_type TEXT,
                  claim_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS fees
                 (user_id INTEGER PRIMARY KEY,
                  total_fee REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS warnings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  reason TEXT,
                  warned_by INTEGER,
                  date TEXT)''')
    
    try:
        c.execute('SELECT claim_time FROM active_tickets LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE active_tickets ADD COLUMN claim_time TEXT')
    
    for ex_type in ['I2C', 'C2I', 'N2C', 'C2N']:
        c.execute('INSERT OR IGNORE INTO rates VALUES (?, ?)', (ex_type, 1.0))
    conn.commit()
    conn.close()
init_db()

class ExchangeTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="I2C", description="INR to Crypto", emoji="<:inrswap:1444194680244797491>"),
            discord.SelectOption(label="C2I", description="Crypto to INR", emoji="<:inrswap:1444194680244797491>"),
            discord.SelectOption(label="N2C", description="NPR to Crypto", emoji="<:cryptoo:1444194918166958120>"),
            discord.SelectOption(label="C2N", description="Crypto to NPR", emoji="<:cryptoo:1444194918166958120>")
        ]
        super().__init__(placeholder="Select exchange type...", options=options, custom_id="exchange_type_select", min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        exchange_type = self.values[0]
        modal = AmountModal(exchange_type)
        await interaction.response.send_modal(modal)
        
        await asyncio.sleep(3)
        
        for option in self.options:
            option.default = False
        
        await interaction.message.edit(view=self.view)

class ExchangePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ExchangeTypeSelect())

@bot.event
async def on_ready():
    print(f'{bot.user} is ready!')
    bot.add_view(ExchangePanelView())
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands')
    except Exception as e:
        print(f'Error syncing: {e}')
@bot.tree.command(name="create", description="Create a new exchanger")
@app_commands.describe(
    user="The user to add as exchanger", 
    security_holding="Security holding in USD",
    i2c="INR to Crypto",
    c2i="Crypto to INR",
    n2c="NPR to Crypto",
    c2n="Crypto to NPR"
)
async def create_exchanger(
    interaction: discord.Interaction, 
    user: discord.Member, 
    security_holding: float,
    i2c: bool = False,
    c2i: bool = False,
    n2c: bool = False,
    c2n: bool = False
):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    types_list = []
    if i2c:
        types_list.append('I2C')
    if c2i:
        types_list.append('C2I')
    if n2c:
        types_list.append('N2C')
    if c2n:
        types_list.append('C2N')
    
    if not types_list:
        await interaction.followup.send("❌ Please select at least one exchanger type!", ephemeral=True)
        return
    
    role_names = {
        'I2C': '# I2C Exchanger',
        'C2I': '# C2I Exchanger',
        'N2C': '# N2C Exchanger',
        'C2N': '# C2N Exchanger'
    }
    
    default_role = interaction.guild.get_role(1443936662018068500)
    if default_role:
        await user.add_roles(default_role)
    
    for exchanger_type in types_list:
        role = discord.utils.get(interaction.guild.roles, name=role_names[exchanger_type])
        if role:
            await user.add_roles(role)
    
    ist = pytz.timezone('Asia/Kolkata')
    joined_date = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    exchanger_type_str = ','.join(types_list)
    c.execute('INSERT OR REPLACE INTO exchangers VALUES (?, ?, ?, ?)', (user.id, security_holding, exchanger_type_str, joined_date))
    conn.commit()
    conn.close()
    
    await interaction.followup.send(f"✅ {user.mention} added as {exchanger_type_str} exchanger with ${security_holding} security holding", ephemeral=True)
@bot.tree.command(name="update", description="Update an exchanger")
@app_commands.describe(
    user="The user to update", 
    security_holding="New security holding in USD",
    i2c="INR to Crypto",
    c2i="Crypto to INR",
    n2c="NPR to Crypto",
    c2n="Crypto to NPR"
)
async def update_exchanger(
    interaction: discord.Interaction, 
    user: discord.Member, 
    security_holding: float,
    i2c: bool = False,
    c2i: bool = False,
    n2c: bool = False,
    c2n: bool = False
):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    types_list = []
    if i2c:
        types_list.append('I2C')
    if c2i:
        types_list.append('C2I')
    if n2c:
        types_list.append('N2C')
    if c2n:
        types_list.append('C2N')
    
    if not types_list:
        await interaction.followup.send("❌ Please select at least one exchanger type!", ephemeral=True)
        return
    
    role_names = {
        'I2C': '# I2C Exchanger',
        'C2I': '# C2I Exchanger',
        'N2C': '# N2C Exchanger',
        'C2N': '# C2N Exchanger'
    }
    
    all_exchanger_roles = [discord.utils.get(interaction.guild.roles, name=name) for name in role_names.values()]
    for role in all_exchanger_roles:
        if role and role in user.roles:
            await user.remove_roles(role)
    
    for exchanger_type in types_list:
        role = discord.utils.get(interaction.guild.roles, name=role_names[exchanger_type])
        if role:
            await user.add_roles(role)
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    exchanger_type_str = ','.join(types_list)
    c.execute('UPDATE exchangers SET security_holding = ?, exchanger_type = ? WHERE user_id = ?', 
              (security_holding, exchanger_type_str, user.id))
    conn.commit()
    conn.close()
    
    await interaction.followup.send(f"✅ Updated {user.mention}: ${security_holding} - {exchanger_type_str}", ephemeral=True)
@bot.tree.command(name="setrates", description="Set exchange rates")
@app_commands.describe(c2i="C2I rate", i2c="I2C rate", n2c="N2C rate", c2n="C2N rate")
async def set_rates(interaction: discord.Interaction, c2i: float = None, i2c: float = None, n2c: float = None, c2n: float = None):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    updates = []
    if c2i is not None:
        c.execute('UPDATE rates SET rate = ? WHERE type = ?', (c2i, 'C2I'))
        updates.append(f"C2I = {c2i}")
    if i2c is not None:
        c.execute('UPDATE rates SET rate = ? WHERE type = ?', (i2c, 'I2C'))
        updates.append(f"I2C = {i2c}")
    if n2c is not None:
        c.execute('UPDATE rates SET rate = ? WHERE type = ?', (n2c, 'N2C'))
        updates.append(f"N2C = {n2c}")
    if c2n is not None:
        c.execute('UPDATE rates SET rate = ? WHERE type = ?', (c2n, 'C2N'))
        updates.append(f"C2N = {c2n}")
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Rates updated: {', '.join(updates)}", ephemeral=True)
@bot.tree.command(name="rates", description="Display all exchange rates")
async def show_rates(interaction: discord.Interaction):
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT type, rate FROM rates')
    rates_data = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    embed = discord.Embed(
        title="<:thumb:1444212018147233943> Exchange Rates",
        description="Current exchange rates for all types",
        color=discord.Color.blue()
    )
    
    inr_rates = f"> **I2C:** {rates_data.get('I2C', 'N/A')}/$\n> **C2I:** {rates_data.get('C2I', 'N/A')}/$"
    npr_rates = f"> **N2C:** {rates_data.get('N2C', 'N/A')}/$\n> **C2N:** {rates_data.get('C2N', 'N/A')}/$"
    
    embed.add_field(name="<:inrswap:1444194680244797491> INR Rates", value=inr_rates, inline=False)
    embed.add_field(name="<:cryptoo:1444194918166958120> NPR Rates", value=npr_rates, inline=False)
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
    
    await interaction.response.send_message(embed=embed)

@bot.command(name="calc")
async def calc(ctx, *, expression: str):
    try:
        expression = expression.replace(' ', '')
        
        allowed_chars = set('0123456789+-*/.()%')
        if not all(c in allowed_chars for c in expression):
            await ctx.send("❌ Invalid characters! Use only numbers and operators (+, -, *, /, %, ())")
            return
        
        result = eval(expression)
        
        embed = discord.Embed(title="🧮 Calculator", color=discord.Color.green())
        embed.add_field(name="Expression", value=f"`{expression}`", inline=False)
        embed.add_field(name="Result", value=f"**{result}**", inline=False)
        
        await ctx.send(embed=embed)
    except ZeroDivisionError:
        await ctx.send("❌ Error: Division by zero!")
    except Exception as e:
        await ctx.send(f"❌ Error: Invalid expression!")

@bot.tree.command(name="convert", description="Convert between currencies")
@app_commands.describe(exchange_type="Exchange type", amount="Amount to convert")
@app_commands.choices(exchange_type=[
    app_commands.Choice(name="I2C (INR to Crypto)", value="I2C"),
    app_commands.Choice(name="C2I (Crypto to INR)", value="C2I"),
    app_commands.Choice(name="N2C (NPR to Crypto)", value="N2C"),
    app_commands.Choice(name="C2N (Crypto to NPR)", value="C2N")
])
async def convert(interaction: discord.Interaction, exchange_type: str, amount: float):
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT rate FROM rates WHERE type = ?', (exchange_type,))
    rate_result = c.fetchone()
    conn.close()
    
    if not rate_result:
        await interaction.response.send_message("❌ Rate not found!", ephemeral=True)
        return
    
    rate = rate_result[0]
    
    if exchange_type == "I2C":
        converted = amount / rate
        result = f"₹{amount:.2f} INR = ${converted:.2f} USD (Rate: {rate})"
    elif exchange_type == "C2I":
        converted = amount * rate
        result = f"${amount:.2f} USD = ₹{converted:.2f} INR (Rate: {rate})"
    elif exchange_type == "N2C":
        converted = amount / rate
        result = f"रू{amount:.2f} NPR = ${converted:.2f} USD (Rate: {rate})"
    else:
        converted = amount * rate
        result = f"${amount:.2f} USD = रू{converted:.2f} NPR (Rate: {rate})"
    
    await interaction.response.send_message(result)

class AmountModal(discord.ui.Modal):
    def __init__(self, exchange_type: str):
        super().__init__(title=f"{exchange_type} Exchange")
        self.exchange_type = exchange_type
        if exchange_type == "I2C":
            currency = "INR"
        elif exchange_type == "N2C":
            currency = "NPR"
        else:
            currency = "USD"
        self.amount_input = discord.ui.TextInput(
            label=f"Amount in {currency}",
            placeholder=f"Enter amount in {currency}",
            required=True
        )
        self.add_item(self.amount_input)
        self.crypto_input = discord.ui.TextInput(
            label="Which Crypto?",
            placeholder="e.g., BTC, ETH, USDT",
            required=True
        )
        self.add_item(self.crypto_input)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount!", ephemeral=True)
            return
        crypto = self.crypto_input.value
        
        conn = sqlite3.connect('exchangers.db')
        c = conn.cursor()
        
        c.execute('SELECT channel_id FROM active_tickets WHERE client_id = ?', (interaction.user.id,))
        existing_ticket = c.fetchone()
        if existing_ticket:
            await interaction.response.send_message("❌ You already have an active ticket! Please complete or close it first.", ephemeral=True)
            conn.close()
            return
        
        c.execute('SELECT rate FROM rates WHERE type = ?', (self.exchange_type,))
        rate_result = c.fetchone()
        conn.close()
        rate = rate_result[0] if rate_result else 1.0
        if self.exchange_type == "I2C":
            amount_inr = amount
            amount_usd = amount / rate
            amount_npr = None
        elif self.exchange_type == "N2C":
            amount_npr = amount
            amount_usd = amount / rate
            amount_inr = None
        elif self.exchange_type == "C2I":
            amount_usd = amount
            amount_inr = amount * rate
            amount_npr = None
        else:  # C2N
            amount_usd = amount
            amount_npr = amount * rate
            amount_inr = None
        embed = discord.Embed(title="<:tickets:1444196138893840425> Ticket Details", color=discord.Color.gold())
        embed.add_field(name="User", value=interaction.user.mention, inline=False)
        embed.add_field(name="Type", value=self.exchange_type, inline=False)
        embed.add_field(name="Crypto", value=crypto, inline=True)
        embed.add_field(name="Amount in USD", value=f"${amount_usd:.2f}", inline=True)
        if amount_inr is not None:
            embed.add_field(name="Amount in INR", value=f"₹{amount_inr:.2f}", inline=True)
        if amount_npr is not None:
            embed.add_field(name="Amount in NPR", value=f"रू{amount_npr:.2f}", inline=True)
        embed.add_field(name="Rules", value="1. Follow server guidelines\n2. Be respectful\n3. Provide accurate information\n4. Wait for exchanger response", inline=False)
        view = ConfirmView(self.exchange_type, amount_usd, amount_inr if amount_inr else amount_npr, interaction.user, crypto)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
class ConfirmView(discord.ui.View):
    def __init__(self, exchange_type: str, amount_usd: float, amount_local: float, user: discord.Member, crypto: str):
        super().__init__(timeout=300)
        self.exchange_type = exchange_type
        self.amount_usd = amount_usd
        self.amount_local = amount_local
        self.user = user
        self.crypto = crypto
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        
        guild = interaction.guild
        
        category_ids = {
            'I2C': 1444172151237378088,
            'C2I': 1444172197164748851,
            'N2C': 1444172222846603346,
            'C2N': 1444172246255145111
        }
        category = guild.get_channel(category_ids[self.exchange_type])
        
        ticket_name = f"uc-{self.exchange_type.lower()}-{self.user.name}"
        role_names = {
            'I2C': '# I2C Exchanger',
            'C2I': '# C2I Exchanger',
            'N2C': '# N2C Exchanger',
            'C2N': '# C2N Exchanger'
        }
        exchanger_role = discord.utils.get(guild.roles, name=role_names[self.exchange_type])
        staff_role = guild.get_role(1443936660063518770)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if exchanger_role:
            overwrites[exchanger_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        ticket_channel = await guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites
        )
        
        conn = sqlite3.connect('exchangers.db')
        c = conn.cursor()
        c.execute('INSERT INTO active_tickets (channel_id, client_id, exchanger_id, exchange_type, claim_time) VALUES (?, ?, ?, ?, ?)',
                  (ticket_channel.id, self.user.id, None, self.exchange_type, None))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(title="<:cryptoswap:1425071000139202620> New Exchange Ticket", color=discord.Color.green())
        embed.add_field(name="User", value=self.user.mention, inline=False)
        embed.add_field(name="Type", value=self.exchange_type, inline=False)
        embed.add_field(name="Crypto", value=self.crypto, inline=True)
        embed.add_field(name="Amount in USD", value=f"${self.amount_usd:.2f}", inline=True)
        if self.exchange_type in ['I2C', 'C2I']:
            embed.add_field(name="Amount in INR", value=f"₹{self.amount_local:.2f}", inline=True)
        else:
            embed.add_field(name="Amount in NPR", value=f"रू{self.amount_local:.2f}", inline=True)
        embed.add_field(name="Rules", value="1. Follow server guidelines\n2. Be respectful\n3. Provide accurate information\n4. Wait for exchanger response", inline=False)
        mention_text = f"{self.user.mention}"
        if exchanger_role:
            mention_text += f" {exchanger_role.mention}"
        await ticket_channel.send(content=mention_text, embed=embed)
        await interaction.edit_original_response(content=f"✅ Ticket created: {ticket_channel.mention}", embed=None, view=None)
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Ticket creation cancelled", view=self)
@bot.tree.command(name="expanel", description="Send the exchange panel")
async def panel(interaction: discord.Interaction):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT type, rate FROM rates')
    rates = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    embed = discord.Embed(
        title="<:cryptoswap:1425071000139202620> Exchange Panel",
        description="Select an exchange type below to create a ticket",
        color=discord.Color.blue()
    )
    
    inr_rates = f"> **I2C:** {rates.get('I2C', 'N/A')}/$\n> **C2I:** {rates.get('C2I', 'N/A')}/$"
    npr_rates = f"> **N2C:** {rates.get('N2C', 'N/A')}/$\n> **C2N:** {rates.get('C2N', 'N/A')}/$"
    tos_details = f"> 1. Fixed Rates – No Negotiations. \n> 2. Always Follow Staff Instructions. \n> 3. Be Patient & Avoid Unnecessary Pings. \n> 4. Read TOS before proceeding."
    
    embed.add_field(name="<:inrswap:1444194680244797491> INR Rates", value=inr_rates, inline=False)
    embed.add_field(name="<:cryptoo:1444194918166958120> NPR Rates", value=npr_rates, inline=False)
    embed.add_field(name="<:rules:1444204795085983775> TOS", value=tos_details, inline=False)
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
     
    view = ExchangePanelView()
    await interaction.response.send_message(f"Panel Sent !!",ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)
@bot.command(name="claim")
async def claim_ticket(ctx):
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT security_holding, exchanger_type FROM exchangers WHERE user_id = ?', (ctx.author.id,))
    result = c.fetchone()
    
    if not result:
        await ctx.send("❌ You are not registered as an exchanger!")
        conn.close()
        return
    
    security_holding, exchanger_types_str = result
    exchanger_types = [t.strip() for t in exchanger_types_str.split(',')]
    
    channel_name = ctx.channel.name
    if not channel_name.startswith("uc-"):
        await ctx.send("❌ This is not a ticket channel!")
        conn.close()
        return
    
    c.execute('SELECT exchanger_id FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    ticket_data = c.fetchone()
    
    if ticket_data and ticket_data[0]:
        if ticket_data[0] == ctx.author.id:
            await ctx.send("❌ You have already claimed this ticket! Please complete it first.")
        else:
            await ctx.send("❌ This ticket has already been claimed by another exchanger!")
        conn.close()
        return
    
    parts = channel_name.split('-')
    if len(parts) < 3:
        await ctx.send("❌ Invalid ticket channel format!")
        conn.close()
        return
    
    ticket_type = parts[1].upper()
    
    if ticket_type not in exchanger_types:
        await ctx.send(f"❌ You can only claim {', '.join(exchanger_types)} tickets! This is a {ticket_type} ticket.")
        conn.close()
        return
    
    c.execute('SELECT channel_id FROM active_tickets WHERE exchanger_id = ?', (ctx.author.id,))
    existing_claim = c.fetchone()
    
    if existing_claim:
        await ctx.send("❌ You already have an active claimed ticket! Please complete it first.")
        conn.close()
        return
    
    conn.close()
    
    async for message in ctx.channel.history(limit=10, oldest_first=True):
        if message.embeds:
            embed_data = message.embeds[0]
            for field in embed_data.fields:
                if field.name == "Amount in USD":
                    amount_str = field.value.replace("$", "").replace(",", "")
                    try:
                        ticket_amount = float(amount_str)
                    except ValueError:
                        await ctx.send("❌ Could not parse ticket amount!")
                        return
                    if ticket_amount > security_holding / 2:
                        await ctx.send(f"❌ Ticket Amount Exceed your limit.\nYour limit: ${security_holding / 2:.2f}\nTicket amount: ${ticket_amount:.2f}")
                        return
                    
                    username = parts[2]
                    new_name = f"c-{ticket_type.lower()}-{username}-{ctx.author.name}"
                    
                    ist = pytz.timezone('Asia/Kolkata')
                    claim_time = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
                    
                    conn = sqlite3.connect('exchangers.db')
                    c = conn.cursor()
                    c.execute('UPDATE active_tickets SET exchanger_id = ?, claim_time = ? WHERE channel_id = ?', 
                              (ctx.author.id, claim_time, ctx.channel.id))
                    conn.commit()
                    conn.close()
                    
                    embed = discord.Embed(
                        title="✅ Ticket Claimed!",
                        description=f"This ticket has been claimed by {ctx.author.mention}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Exchanger", value=ctx.author.mention, inline=True)
                    embed.add_field(name="Amount", value=f"${ticket_amount:.2f}", inline=True)
                    embed.set_footer(text=f"Claimed at {claim_time} IST")
                    
                    await ctx.send(embed=embed)
                    
                    try:
                        await ctx.channel.edit(name=new_name)
                    except discord.HTTPException as e:
                        if e.status == 429:
                            await ctx.send("⏳ Channel will be renamed shortly due to rate limiting...")
                        else:
                            pass
                    
                    return
    await ctx.send("❌ Could not find ticket information!")



class FeedbackModal(discord.ui.Modal):
    def __init__(self, exchanger_id: int, exchange_type: str):
        super().__init__(title="Give Feedback")
        self.exchanger_id = exchanger_id
        self.exchange_type = exchange_type
        
        self.rating_input = discord.ui.TextInput(
            label="Rating (1-5)",
            placeholder="Enter a number from 1 to 5",
            required=True,
            max_length=1
        )
        self.add_item(self.rating_input)
        
        self.feedback_input = discord.ui.TextInput(
            label="Feedback",
            placeholder="Share your experience...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.feedback_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating_input.value)
            if rating < 1 or rating > 5:
                await interaction.response.send_message("❌ Rating must be between 1 and 5!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Rating must be a number between 1 and 5!", ephemeral=True)
            return
        
        stars = "⭐" * rating
        feedback_text = self.feedback_input.value
        
        feedback_channel = interaction.guild.get_channel(1443940712482869440)
        if feedback_channel:
            exchanger = await interaction.guild.fetch_member(self.exchanger_id)
            
            embed = discord.Embed(
                title="<:love:1444213564175810592> Sky -  New Feedback",
                color=discord.Color.gold()
            )
            embed.add_field(name="Exchanger", value=exchanger.mention, inline=True)
            embed.add_field(name="Exchange Type", value=self.exchange_type, inline=True)
            embed.add_field(name="Rating", value=stars, inline=False)
            embed.add_field(name="Feedback", value=feedback_text, inline=False)
            embed.set_footer(text=f"Sky - Best Exchange Server !")
            
            await feedback_channel.send(embed=embed)
        
        await interaction.response.send_message("✅ Thank you for your feedback!", ephemeral=True)

class VouchButtonView(discord.ui.View):
    def __init__(self, exchanger_id: int, exchange_type: str, from_currency: str, to_currency: str, amount_usd: float, amount_local: float, crypto: str = None):
        super().__init__(timeout=None)
        self.exchanger_id = exchanger_id
        self.exchange_type = exchange_type
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.amount_usd = amount_usd
        self.amount_local = amount_local
        self.crypto = crypto
    
    @discord.ui.button(label="Copy Vouch", style=discord.ButtonStyle.blurple, emoji="📋", custom_id="vouch_button")
    async def vouch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.exchange_type in ["I2C", "N2C"]:
            currency_symbol = "₹" if self.exchange_type == "I2C" else "रू"
            payment_method = "UPI" if self.exchange_type == "I2C" else "Esewa"
            crypto_name = self.crypto if self.crypto else "Crypto"
            vouch_format = f"+rep {self.exchanger_id} Legit {self.exchange_type} Exchange of {currency_symbol}{self.amount_local:.2f} {payment_method} to ${self.amount_usd:.2f} {crypto_name} | TY !!"
        else:
            currency_symbol = "₹" if self.exchange_type == "C2I" else "रू"
            payment_method = "UPI" if self.exchange_type == "C2I" else "Esewa"
            crypto_name = self.crypto if self.crypto else "Crypto"
            vouch_format = f"+rep {self.exchanger_id} Legit {self.exchange_type} Exchange of ${self.amount_usd:.2f} {crypto_name} to {currency_symbol}{self.amount_local:.2f} {payment_method} | TY !!"
        await interaction.response.send_message(f"{vouch_format}", ephemeral=True)
    
    @discord.ui.button(label="Give Feedback", style=discord.ButtonStyle.green, emoji="📝", custom_id="feedback_button")
    async def feedback_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FeedbackModal(self.exchanger_id, self.exchange_type)
        await interaction.response.send_modal(modal)

@bot.command(name="unclaim")
async def unclaim_ticket(ctx):
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM exchangers WHERE user_id = ?', (ctx.author.id,))
    if not c.fetchone():
        await ctx.send("❌ You must be an exchanger to use this command!")
        conn.close()
        return
    conn.close()
    
    channel_name = ctx.channel.name
    if not channel_name.startswith("c-"):
        await ctx.send("❌ This is not a claimed ticket channel!")
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT exchanger_id, claim_time FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    ticket_data = c.fetchone()
    conn.close()
    
    if not ticket_data or not ticket_data[0]:
        await ctx.send("❌ This ticket is not claimed!")
        return
    
    exchanger_id, claim_time_str = ticket_data
    
    if exchanger_id != ctx.author.id:
        await ctx.send("❌ Only the claimer can unclaim this ticket!")
        return
    
    if claim_time_str:
        ist = pytz.timezone('Asia/Kolkata')
        claim_time = datetime.strptime(claim_time_str, '%Y-%m-%d %H:%M:%S')
        claim_time = ist.localize(claim_time)
        current_time = datetime.now(ist)
        time_diff = (current_time - claim_time).total_seconds() / 60
        
        if time_diff < 5:
            remaining = 5 - time_diff
            await ctx.send(f"❌ You can only unclaim after 5 minutes! Please wait {remaining:.1f} more minutes.")
            return
    
    parts = channel_name.split('-')
    ticket_type = None
    if len(parts) >= 4:
        ticket_type = parts[1].upper()
        username = parts[2]
        new_name = f"uc-{parts[1]}-{username}"
        await ctx.channel.edit(name=new_name)
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('UPDATE active_tickets SET exchanger_id = ?, claim_time = ? WHERE channel_id = ?', 
              (None, None, ctx.channel.id))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(
        title="🔓 Ticket Unclaimed",
        description=f"{ctx.author.mention} has unclaimed this ticket.\n\nIf you wish, you may claim it now!",
        color=discord.Color.orange()
    )
    
    role_names = {
        'I2C': '# I2C Exchanger',
        'C2I': '# C2I Exchanger',
        'N2C': '# N2C Exchanger',
        'C2N': '# C2N Exchanger'
    }
    
    mention_text = ""
    if ticket_type and ticket_type in role_names:
        exchanger_role = discord.utils.get(ctx.guild.roles, name=role_names[ticket_type])
        if exchanger_role:
            mention_text = exchanger_role.mention
    
    await ctx.send(content=mention_text, embed=embed)

@bot.command(name="notify")
async def notify_client(ctx):
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM exchangers WHERE user_id = ?', (ctx.author.id,))
    if not c.fetchone():
        await ctx.send("❌ You must be an exchanger to use this command!")
        conn.close()
        return
    
    c.execute('SELECT client_id FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    ticket_data = c.fetchone()
    conn.close()
    
    if not ticket_data:
        await ctx.send("❌ This is not a ticket channel!")
        return
    
    client_id = ticket_data[0]
    client = await ctx.guild.fetch_member(client_id)
    
    try:
        embed = discord.Embed(
            title="📢 Ticket Notification",
            description=f"Please check your ticket in {ctx.channel.mention} as soon as possible!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Exchanger", value=ctx.author.mention, inline=True)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.set_footer(text=f"Notification from {ctx.guild.name}")
        
        await client.send(embed=embed)
        await ctx.send(f"✅ Notification sent to {client.mention}!")
    except discord.Forbidden:
        await ctx.send(f"❌ Could not send DM to {client.mention}. They may have DMs disabled.")
    except Exception as e:
        await ctx.send(f"❌ Failed to send notification: {str(e)}")

@bot.command(name="done")
async def done_ticket(ctx):
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM exchangers WHERE user_id = ?', (ctx.author.id,))
    if not c.fetchone():
        await ctx.send("❌ You must be an exchanger to use this command!")
        conn.close()
        return
    conn.close()
    
    channel_name = ctx.channel.name
    if not (channel_name.startswith("uc-") or channel_name.startswith("c-")):
        await ctx.send("❌ This is not a ticket channel!")
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT exchanger_id FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    ticket_data = c.fetchone()
    conn.close()
    
    if not ticket_data or not ticket_data[0]:
        await ctx.send("❌ This ticket has not been claimed yet!")
        return
    
    claimer_id = ticket_data[0]
    
    if claimer_id != ctx.author.id:
        await ctx.send("❌ Only the claimer can mark this ticket as done!")
        return
    exchanger_id = None
    client_id = None
    exchange_type = None
    crypto = None
    amount_usd = None
    amount_inr = None
    amount_npr = None
    async for message in ctx.channel.history(limit=10, oldest_first=True):
        if message.embeds:
            embed = message.embeds[0]
            for field in embed.fields:
                if field.name == "User":
                    user_mention = field.value
                    if "<@" in user_mention:
                        client_id = int(user_mention.replace("<@", "").replace(">", "").replace("!", ""))
                elif field.name == "Type":
                    exchange_type = field.value
                elif field.name == "Crypto":
                    crypto = field.value
                elif field.name == "Amount in USD":
                    amount_str = field.value.replace("$", "").replace(",", "")
                    try:
                        amount_usd = float(amount_str)
                    except ValueError:
                        pass
                elif field.name == "Amount in INR":
                    amount_str = field.value.replace("₹", "").replace(",", "")
                    try:
                        amount_inr = float(amount_str)
                    except ValueError:
                        pass
                elif field.name == "Amount in NPR":
                    amount_str = field.value.replace("रू", "").replace(",", "")
                    try:
                        amount_npr = float(amount_str)
                    except ValueError:
                        pass
            exchanger_id = claimer_id
            break
    if not exchange_type or not exchanger_id or not client_id or not amount_usd:
        await ctx.send("❌ Could not find ticket information!")
        return
    ist = pytz.timezone('Asia/Kolkata')
    trade_date = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('INSERT INTO trades (exchanger_id, client_id, exchange_type, amount_usd, crypto, date) VALUES (?, ?, ?, ?, ?, ?)',
              (exchanger_id, client_id, exchange_type, amount_usd, crypto, trade_date))
    
    c.execute('INSERT OR IGNORE INTO fees (user_id, total_fee) VALUES (?, 0)', (exchanger_id,))
    c.execute('UPDATE fees SET total_fee = total_fee + 0.025 WHERE user_id = ?', (exchanger_id,))
    
    conn.commit()
    conn.close()
    guild = ctx.guild
    client = await guild.fetch_member(client_id)
    exchanger = await guild.fetch_member(exchanger_id)
    role_names = {
        'I2C': '# I2C',
        'C2I': '# C2I',
        'N2C': '# N2C',
        'C2N': '# C2N'
    }
    client_role = discord.utils.get(guild.roles, name=role_names.get(exchange_type, ''))
    if client_role:
        await client.add_roles(client_role)
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT SUM(amount_usd) FROM trades WHERE client_id = ?', (client_id,))
    client_total = c.fetchone()[0] or 0.0
    if client_total >= 1000:
        role = guild.get_role(1443936663947579402)
        if role:
            await client.add_roles(role)
    elif client_total >= 500:
        role = guild.get_role(1443936664035659819)
        if role:
            await client.add_roles(role)
    elif client_total >= 100:
        role = guild.get_role(1443937344808816680)
        if role:
            await client.add_roles(role)
    elif client_total > 0:
        role = guild.get_role(1443937345849135224)
        if role:
            await client.add_roles(role)
    c.execute('SELECT SUM(amount_usd) FROM trades WHERE exchanger_id = ?', (exchanger_id,))
    exchanger_total = c.fetchone()[0] or 0.0
    if exchanger_total >= 1200:
        role = guild.get_role(1443936660680216688)
        if role:
            await exchanger.add_roles(role)
    elif exchanger_total >= 400:
        role = guild.get_role(1443936661250642021)
        if role:
            await exchanger.add_roles(role)
    conn.close()
    if exchange_type in ["I2C", "N2C"]:
        from_currency = "UPI" if exchange_type == "I2C" else "Esewa"
        to_currency = crypto if crypto else "Crypto"
        amount_local = amount_inr if amount_inr else amount_npr
    else:  # C2I or C2N
        from_currency = crypto if crypto else "Crypto"
        to_currency = "UPI" if exchange_type == "C2I" else "Esewa"
        amount_local = amount_inr if amount_inr else amount_npr
    embed = discord.Embed(
        title="<:thumb:1444212018147233943> Deal Completed!",
        description=f"This deal has been completed by {exchanger.mention} for {amount_local:.2f} {from_currency} to ${amount_usd:.2f} {to_currency}. We kindly request you to vouch and give feedback which means a lot to us!",
        color=discord.Color.green()
    )
    view = VouchButtonView(exchanger_id, exchange_type, from_currency, to_currency, amount_usd, amount_local, crypto)
    await ctx.send(f"{exchanger.mention}{client.mention}",embed=embed, view=view)
    log_channel = guild.get_channel(1444179898737361109)
    if log_channel:
        exchanger = await guild.fetch_member(exchanger_id)
        log_embed = discord.Embed(
            title="<:thumb:1444212018147233943> Deal Completed",
            color=discord.Color.blue(),
            timestamp=datetime.now(ist)
        )
        log_embed.add_field(name="Exchanger", value=exchanger.mention, inline=True)
        log_embed.add_field(name="Client", value=client.mention, inline=True)
        log_embed.add_field(name="Type", value=exchange_type, inline=True)
        log_embed.add_field(name="Crypto", value=crypto, inline=True)
        log_embed.add_field(name="Amount (USD)", value=f"${amount_usd:.2f}", inline=True)
        log_embed.add_field(name="Date (IST)", value=trade_date, inline=True)
        await log_channel.send(embed=log_embed)
    
    public_log_channel = guild.get_channel(1444222323124342945)
    if public_log_channel:
        exchanger = await guild.fetch_member(exchanger_id)
        public_embed = discord.Embed(
            title="<:thumb:1444212018147233943> Deal Completed",
            color=discord.Color.green(),
            timestamp=datetime.now(ist)
        )
        public_embed.add_field(name="Exchanger", value=exchanger.mention, inline=True)
        public_embed.add_field(name="Client", value="Anonymous", inline=True)
        public_embed.add_field(name="Type", value=exchange_type, inline=True)
        public_embed.add_field(name="Crypto", value=crypto, inline=True)
        public_embed.add_field(name="Amount (USD)", value=f"${amount_usd:.2f}", inline=True)
        public_embed.add_field(name="Date (IST)", value=trade_date, inline=True)
        await public_log_channel.send(embed=public_embed)
    done_category = discord.utils.get(guild.categories, name="# Done")
    if done_category:
        await ctx.channel.edit(category=done_category)
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('DELETE FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    conn.commit()
    conn.close()

@bot.tree.command(name="forceclose", description="Force close a ticket and delete it")
async def forceclose(interaction: discord.Interaction):
    channel_name = interaction.channel.name
    if not (channel_name.startswith("uc-") or channel_name.startswith("c-")):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return
    
    await interaction.response.send_message("🗑️ Force closing ticket and deleting channel...", ephemeral=True)
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('DELETE FROM active_tickets WHERE channel_id = ?', (interaction.channel.id,))
    conn.commit()
    conn.close()
    
    await interaction.channel.delete()

@bot.command(name="close")
async def close_ticket(ctx):
    staff_role = ctx.guild.get_role(1443936660063518770)
    if not staff_role or staff_role not in ctx.author.roles:
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    channel_name = ctx.channel.name
    if not (channel_name.startswith("uc-") or channel_name.startswith("c-")):
        await ctx.send("❌ This is not a ticket channel!")
        return
    
    await ctx.send("📝 Creating transcript and closing ticket...")
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT client_id, exchanger_id FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    ticket_data = c.fetchone()
    c.execute('DELETE FROM active_tickets WHERE channel_id = ?', (ctx.channel.id,))
    conn.commit()
    conn.close()
    
    client_id = ticket_data[0] if ticket_data else None
    exchanger_id = ticket_data[1] if ticket_data and ticket_data[1] else None
    
    try:
        transcript = await chat_exporter.export(ctx.channel)
        
        if transcript:
            transcript_file = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{ctx.channel.name}.html"
            )
            
            transcript_channel = ctx.guild.get_channel(1444225280397938850)
            if transcript_channel:
                embed = discord.Embed(
                    title="📋 Ticket Transcript",
                    description=f"Transcript for {ctx.channel.mention}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Closed by", value=ctx.author.mention, inline=True)
                embed.add_field(name="Channel", value=ctx.channel.name, inline=True)
                
                ist = pytz.timezone('Asia/Kolkata')
                close_time = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
                embed.add_field(name="Closed at", value=close_time, inline=False)
                
                await transcript_channel.send(embed=embed, file=transcript_file)
            
            if client_id:
                try:
                    client = await ctx.guild.fetch_member(client_id)
                    transcript_file_client = discord.File(
                        io.BytesIO(transcript.encode()),
                        filename=f"transcript-{ctx.channel.name}.html"
                    )
                    await client.send(
                        f"📋 Your ticket **{ctx.channel.name}** has been closed by staff.\nHere's the transcript:",
                        file=transcript_file_client
                    )
                except:
                    pass
            
            if exchanger_id:
                try:
                    exchanger = await ctx.guild.fetch_member(exchanger_id)
                    transcript_file_exchanger = discord.File(
                        io.BytesIO(transcript.encode()),
                        filename=f"transcript-{ctx.channel.name}.html"
                    )
                    await exchanger.send(
                        f"📋 Ticket **{ctx.channel.name}** has been closed by staff.\nHere's the transcript:",
                        file=transcript_file_exchanger
                    )
                except:
                    pass
    
    except Exception as e:
        await ctx.send(f"⚠️ Error creating transcript: {str(e)}")
    
    await ctx.channel.delete()

class FeeButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Check Fee", style=discord.ButtonStyle.blurple, emoji="<:thaila:1425067683300507669>", custom_id="check_fee_button")
    async def check_fee_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect('exchangers.db')
        c = conn.cursor()
        c.execute('SELECT total_fee FROM fees WHERE user_id = ?', (interaction.user.id,))
        result = c.fetchone()
        conn.close()
        
        total_fee = result[0] if result else 0.0
        
        embed = discord.Embed(
            title="<:thaila:1425067683300507669> Your Fee Balance",
            description=f"You owe **${total_fee:.4f}** in management fees",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="feepanel", description="Send the fee panel")
async def feepanel(interaction: discord.Interaction):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="<:thaila:1425067683300507669> Fee Management Panel",
        description="Click the button below to check your pending fees",
        color=discord.Color.gold()
    )
    embed.add_field(name="Fee Structure", value="$0.025 per completed deal", inline=False)
    
    view = FeeButtonView()
    await interaction.response.send_message("✅ Fee panel sent!", ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)

@bot.tree.command(name="addfee", description="Add fee to an exchanger")
@app_commands.describe(user="The exchanger", amount="Amount to add")
async def addfee(interaction: discord.Interaction, user: discord.Member, amount: float):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO fees (user_id, total_fee) VALUES (?, 0)', (user.id,))
    c.execute('UPDATE fees SET total_fee = total_fee + ? WHERE user_id = ?', (amount, user.id))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Added ${amount:.2f} fee to {user.mention}", ephemeral=True)

@bot.tree.command(name="deductfee", description="Deduct fee from an exchanger")
@app_commands.describe(user="The exchanger", amount="Amount to deduct")
async def deductfee(interaction: discord.Interaction, user: discord.Member, amount: float):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO fees (user_id, total_fee) VALUES (?, 0)', (user.id,))
    c.execute('UPDATE fees SET total_fee = total_fee - ? WHERE user_id = ?', (amount, user.id))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Deducted ${amount:.2f} fee from {user.mention}", ephemeral=True)

@bot.tree.command(name="clearfee", description="Clear all fees for an exchanger")
@app_commands.describe(user="The exchanger")
async def clearfee(interaction: discord.Interaction, user: discord.Member):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('UPDATE fees SET total_fee = 0 WHERE user_id = ?', (user.id,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Cleared all fees for {user.mention}", ephemeral=True)

@bot.tree.command(name="checkfee", description="Check fee balance of an exchanger")
@app_commands.describe(exchanger="The exchanger to check")
async def checkfee(interaction: discord.Interaction, exchanger: discord.Member):
    required_role = interaction.guild.get_role(1443936237349240872)
    if not required_role or required_role not in interaction.user.roles:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT total_fee FROM fees WHERE user_id = ?', (exchanger.id,))
    result = c.fetchone()
    conn.close()
    
    total_fee = result[0] if result else 0.0
    
    embed = discord.Embed(
        title=f"<:thaila:1425067683300507669> Fee Balance - {exchanger.display_name}",
        description=f"{exchanger.mention} owes **${total_fee:.2f}** in management fees",
        color=discord.Color.gold()
    )
    embed.add_field(name="Fee per deal", value="$0.025", inline=True)
    embed.set_thumbnail(url=exchanger.display_avatar.url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="warn")
async def warn_exchanger(ctx, exchanger: discord.Member, *, reason: str):
    required_role = ctx.guild.get_role(1443936660063518770)
    if not required_role or required_role not in ctx.author.roles:
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    ist = pytz.timezone('Asia/Kolkata')
    warn_date = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('INSERT INTO warnings (user_id, reason, warned_by, date) VALUES (?, ?, ?, ?)',
              (exchanger.id, reason, ctx.author.id, warn_date))
    warn_id = c.lastrowid
    
    c.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ?', (exchanger.id,))
    warn_count = c.fetchone()[0]
    
    if warn_count >= 10 and warn_count % 10 == 0:
        c.execute('INSERT OR IGNORE INTO fees (user_id, total_fee) VALUES (?, 0)', (exchanger.id,))
        c.execute('UPDATE fees SET total_fee = total_fee + 1.0 WHERE user_id = ?', (exchanger.id,))
    
    conn.commit()
    conn.close()
    
    warn_channel = ctx.guild.get_channel(1444217997484101702)
    if warn_channel:
        embed = discord.Embed(
            title="⚠️ Warning Issued",
            color=discord.Color.orange()
        )
        embed.add_field(name="Exchanger", value=exchanger.mention, inline=True)
        embed.add_field(name="Warned By", value=ctx.author.mention, inline=True)
        embed.add_field(name="Warn ID", value=f"`{warn_id}`", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=f"{warn_count}", inline=True)
        embed.set_footer(text=f"Date: {warn_date} IST")
        
        if warn_count >= 10 and warn_count % 10 == 0:
            embed.add_field(name="⚠️ Penalty", value="$1.00 added to fee balance", inline=False)
        
        await warn_channel.send(embed=embed)
    
    await ctx.send(f"✅ Warning issued to {exchanger.mention} | Warn ID: `{warn_id}` | Total Warnings: {warn_count}")

@bot.command(name="removewarn")
async def remove_warn(ctx, exchanger: discord.Member, warn_id: int):
    required_role = ctx.guild.get_role(1443936660063518770)
    if not required_role or required_role not in ctx.author.roles:
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM warnings WHERE id = ? AND user_id = ?', (warn_id, exchanger.id))
    if not c.fetchone():
        await ctx.send(f"❌ Warning ID `{warn_id}` not found for {exchanger.mention}!")
        conn.close()
        return
    
    c.execute('DELETE FROM warnings WHERE id = ?', (warn_id,))
    conn.commit()
    conn.close()
    
    await ctx.send(f"✅ Removed warning `{warn_id}` from {exchanger.mention}")

@bot.command(name="clearwarns")
async def clear_warns(ctx, exchanger: discord.Member):
    required_role = ctx.guild.get_role(1443936660063518770)
    if not required_role or required_role not in ctx.author.roles:
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('DELETE FROM warnings WHERE user_id = ?', (exchanger.id,))
    conn.commit()
    conn.close()
    
    await ctx.send(f"✅ Cleared all warnings for {exchanger.mention}")

@bot.command(name="warns")
async def check_warns(ctx, exchanger: discord.Member = None):
    target = exchanger if exchanger else ctx.author
    
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT id, reason, warned_by, date FROM warnings WHERE user_id = ? ORDER BY id DESC', (target.id,))
    warnings = c.fetchall()
    conn.close()
    
    if not warnings:
        await ctx.send(f"✅ {target.mention} has no warnings!")
        return
    
    embed = discord.Embed(
        title=f"⚠️ Warnings - {target.display_name}",
        description=f"Total Warnings: **{len(warnings)}**",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    for warn_id, reason, warned_by, date in warnings[:10]:
        warner = await ctx.guild.fetch_member(warned_by) if warned_by else None
        warner_name = warner.display_name if warner else "Unknown"
        embed.add_field(
            name=f"Warn ID: {warn_id}",
            value=f"**Reason:** {reason}\n**By:** {warner_name}\n**Date:** {date}",
            inline=False
        )
    
    if len(warnings) > 10:
        embed.set_footer(text=f"Showing 10 of {len(warnings)} warnings")
    
    await ctx.send(embed=embed)

@bot.tree.command(name="profile", description="View user profile")
@app_commands.describe(user="The user to view profile (leave empty for yourself)")
async def profile(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user if user else interaction.user
    conn = sqlite3.connect('exchangers.db')
    c = conn.cursor()
    c.execute('SELECT security_holding, exchanger_type, joined_date FROM exchangers WHERE user_id = ?', (target_user.id,))
    exchanger_result = c.fetchone()
    if exchanger_result:
        security_holding, exchanger_type, joined_date = exchanger_result
        c.execute('SELECT COUNT(*), SUM(amount_usd) FROM trades WHERE exchanger_id = ?', (target_user.id,))
        stats = c.fetchone()
        total_exchanges = stats[0] if stats[0] else 0
        total_usd = stats[1] if stats[1] else 0.0
        c.execute('SELECT exchange_type, amount_usd, date FROM trades WHERE exchanger_id = ? ORDER BY id DESC LIMIT 5', (target_user.id,))
        recent_deals = c.fetchall()
        conn.close()
        embed = discord.Embed(
            title=f"<:thaila:1425067683300507669> Exchanger Profile - {target_user.display_name}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="User", value=target_user.mention, inline=True)
        embed.add_field(name="Joined Date", value=joined_date, inline=True)
        embed.add_field(name="Type", value=exchanger_type, inline=True)
        embed.add_field(name="Total Exchanges", value=str(total_exchanges), inline=True)
        embed.add_field(name="Total $ Exchanged", value=f"${total_usd:.2f}", inline=True)
        embed.add_field(name="Security Holding", value=f"${security_holding:.2f}", inline=True)
        if recent_deals:
            deals_text = f""
            for deal in recent_deals:
                deal_type, deal_amount, deal_date = deal
                try:
                    date_obj = datetime.strptime(deal_date, '%Y-%m-%d %H:%M:%S')
                    formatted_date = date_obj.strftime('%d/%m/%Y')
                except:
                    formatted_date = deal_date
                deals_text += f"> **{deal_type}** - ${deal_amount:.2f} - {formatted_date}\n"
            embed.add_field(name="<:zyx_GZ_verified:1414987272918405280> Recent 5 Deals", value=deals_text, inline=False)
        else:
            embed.add_field(name="<:zyx_GZ_verified:1414987272918405280> Recent 5 Deals", value="No deals yet", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        c.execute('SELECT COUNT(*), SUM(amount_usd) FROM trades WHERE client_id = ?', (target_user.id,))
        stats = c.fetchone()
        total_exchanges = stats[0] if stats[0] else 0
        total_usd = stats[1] if stats[1] else 0.0
        conn.close()
        if total_exchanges == 0:
            await interaction.response.send_message(f"❌ {target_user.mention} has no trading history!", ephemeral=True)
            return
        guild = interaction.guild
        highest_role = None
        for role in target_user.roles:
            if role.name != "@everyone":
                if highest_role is None or role.position > highest_role.position:
                    highest_role = role
        embed = discord.Embed(
            title=f"<:cliente:1420041881873678438> Client Profile - {target_user.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="User", value=target_user.mention, inline=True)
        embed.add_field(name="Total Exchanges", value=str(total_exchanges), inline=True)
        embed.add_field(name="Total $ Exchanged", value=f"${total_usd:.2f}", inline=True)
        embed.add_field(name="Highest Role", value=highest_role.mention if highest_role else "None", inline=True)
        await interaction.response.send_message(embed=embed)
bot.run('')
