# Discord Exchange Bot

A Discord bot for managing exchange tickets with SQLite storage.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Replace `YOUR_BOT_TOKEN_HERE` in `bot.py` with your actual Discord bot token

3. Create the required roles in your Discord server:
   - `I2C Exchanger`
   - `C2I Exchanger`
   - `N2C Exchanger`
   - `C2N Exchanger`

4. Update the default role ID (1443936662018068500) in the code if needed

5. Run the bot:
```bash
python bot.py
```

## Commands

- `/create <user> <security_holding> <exchanger_type>` - Add a new exchanger
- `/update <user> <security_holding> <exchanger_type>` - Update an exchanger
- `/panel` - Send the exchange panel with dropdowns
- `/claim` - Claim a ticket (exchangers only)
- `/done` - Mark ticket as done, log trade, give roles, and send vouch button
- `/profile [user]` - View exchanger profile with stats and recent deals
- `/setrates` - Set exchange rates (C2I, I2C, N2C, C2N)
- `/rates` - Display all exchange rates

## Features

- SQLite database for storing exchangers, rates, and trades
- Persistent dropdown menus for exchange type selection
- Modal forms for amount, crypto, and wallet input
- Automatic role assignment for exchangers and clients
- Ticket creation with proper permissions
- Security holding validation for claims
- Trade logging with IST timestamps
- Exchanger profiles with statistics and recent deals
- Client profiles with total exchanges and highest role
- Automatic milestone role assignment:
  - Clients: $100+ / $500+ / $1000+
  - Exchangers: $400+ / $1200+
- Automatic channel movement to "# Done" category
- Deal logs sent to specified channel
- Vouch format button with amounts and currencies
