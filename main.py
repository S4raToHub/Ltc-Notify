import os
import requests
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ----------------- CONFIG -----------------
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_TOKEN")          # put in .env
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")      # put in .env
LTC_ADDRESS = ""
GUILD_ID = 
# ------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

last_hash = None


# --------- Utility functions ----------
def get_ltc_price_usd() -> float:
    try:
        data = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd",
            timeout=10,
        ).json()
        return data["litecoin"]["usd"]
    except Exception as e:
        print("Price fetch error:", e)
        return 0


def get_wallet_info():
    """Fetch full LTC address info (balance, txs, etc.)"""
    try:
        resp = requests.get(
            f"https://api.blockcypher.com/v1/ltc/main/addrs/{LTC_ADDRESS}/full",
            timeout=15,
        ).json()
        return resp
    except Exception as e:
        print("Wallet info error:", e)
        return None


async def send_webhook_notification(hash, ltc_amount, usd_amount, sender, ltc_price):
    webhook = discord.SyncWebhook.from_url(WEBHOOK_URL)
    embed = discord.Embed(title="💰 New LTC Transaction", color=0x00FF00)
    embed.add_field(
        name="Hash",
        value=f"[{hash}](https://live.blockcypher.com/ltc/tx/{hash})",
        inline=False,
    )
    embed.add_field(name="Amount", value=f"{ltc_amount:.8f} LTC (${usd_amount:.2f})", inline=False)
    embed.add_field(name="Sent From", value=sender, inline=False)
    embed.add_field(name="LTC Price", value=f"${ltc_price:.2f}", inline=False)
    webhook.send(embed=embed)


# --------- Background Task ----------
@tasks.loop(seconds=60)
async def transaction_check():
    global last_hash
    data = get_wallet_info()
    if not data or "txs" not in data:
        return

    latest_tx = data["txs"][0]
    latest_hash = latest_tx["hash"]

    if latest_hash != last_hash:
        # calculate how much was received
        ltc_amount = sum(
            o["value"] / 1e8
            for o in latest_tx["outputs"]
            if "addresses" in o and LTC_ADDRESS in o["addresses"]
        )
        if ltc_amount > 0:
            ltc_price = get_ltc_price_usd()
            usd_amount = ltc_amount * ltc_price
            sender = (
                latest_tx["inputs"][0]["addresses"][0]
                if "inputs" in latest_tx and "addresses" in latest_tx["inputs"][0]
                else "Unknown"
            )
            await send_webhook_notification(latest_hash, ltc_amount, usd_amount, sender, ltc_price)

        last_hash = latest_hash


# --------- Commands ----------
@bot.command()
async def balance(ctx):
    """Check total LTC balance & USD value"""
    data = get_wallet_info()
    if not data:
        await ctx.send("⚠️ Could not fetch balance.")
        return

    balance_ltc = data.get("balance", 0) / 1e8
    ltc_price = get_ltc_price_usd()
    usd_value = balance_ltc * ltc_price

    embed = discord.Embed(title="🏦 Wallet Balance", color=0x3498db)
    embed.add_field(name="LTC", value=f"{balance_ltc:.8f} LTC", inline=False)
    embed.add_field(name="USD", value=f"${usd_value:.2f}", inline=False)
    embed.add_field(name="LTC Price", value=f"${ltc_price:.2f}", inline=False)

    await ctx.send(embed=embed)


@bot.command()
async def transactions(ctx, count: int = 5):
    """Show last N transactions"""
    data = get_wallet_info()
    if not data or "txs" not in data:
        await ctx.send("⚠️ Could not fetch transactions.")
        return

    txs = data["txs"][:count]
    embed = discord.Embed(title=f"📜 Last {count} Transactions", color=0x9b59b6)
    for tx in txs:
        tx_hash = tx["hash"]
        ltc_amount = sum(
            o["value"] / 1e8
            for o in tx["outputs"]
            if "addresses" in o and LTC_ADDRESS in o["addresses"]
        )
        embed.add_field(
            name=tx_hash[:10] + "...",
            value=f"{ltc_amount:.8f} LTC\n[View](https://live.blockcypher.com/ltc/tx/{tx_hash})",
            inline=False,
        )
    await ctx.send(embed=embed)


# --------- Events ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    transaction_check.start()


# --------- Run Bot ----------
bot.run(BOT_TOKEN)
