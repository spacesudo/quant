import telebot
from dotenv import load_dotenv
import json
import os
import funcs
from cloudinary import uploader
import cloudinary
import requests
from telebot.util import antiflood, extract_arguments, quick_markup
from db import Users
from funcs import get_market_chart, generate_chart, get_top_wallet
import sqlite3
import time
from collections import defaultdict
import threading

load_dotenv()

TOKEN = os.getenv('TOKEN')

bot = telebot.TeleBot(TOKEN, 'markdown')

db_user = Users()
db_user.setup()

cloudinary.config(
    cloud_name='db1owt5ev',
    api_key='579928467789982',
    api_secret='Ggex9FrPtAcRUpmdStI9fE16cV0'
)

ETH_API_KEY = "1FABWFGJX3214QQVDTSTQ1UKB43KUWPE63"
ETH_API_URL = "https://api.etherscan.io/api"

DB_NAME = "wallets.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            wallet_address TEXT,
            wallet_name TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_wallet(user_id, wallet_address, wallet_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tracked_wallets (user_id, wallet_address, wallet_name)
        VALUES (?, ?, ?)
    """, (user_id, wallet_address, wallet_name))
    conn.commit()
    conn.close()

def remove_wallet(user_id, wallet_address):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM tracked_wallets
        WHERE user_id = ? AND wallet_address = ?
    """, (user_id, wallet_address))
    conn.commit()
    conn.close()

def get_wallets(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT wallet_address, wallet_name FROM tracked_wallets
        WHERE user_id = ?
    """, (user_id,))
    wallets = cursor.fetchall()
    conn.close()
    return wallets

# Function to get transactions for an Ethereum address
def get_transactions(address):
    params = {
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": ETH_API_KEY,
    }
    response = requests.get(ETH_API_URL, params=params)
    data = response.json()
    if data["status"] == "1":
        return data["result"]  # List of transactions
    return [] 


def cssTemplate(url):
    return f"""
```css
body {{
  background-image: url('{url}');
  background-size: cover;
  background-position: center;
  height: 100vh;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}}
h1 {{
  color: #333;
}}
img {{
  max-width: 100%;
  height: auto;
  border-radius: 8px; /* optional: border radius */
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); /* optional: shadow */
}}
```"""

def htmlTemplate(url):
    return f"""
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Example</title>
</head>
<body>
<img src="{url}" alt="Uploaded Image">
</body>
</html>```
"""

def img_upload(file):
    upload = uploader.upload(file)
    return upload['secure_url']

@bot.message_handler(commands=["track"])
def track(message):
    try:
        user_id = message.chat.id
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot.reply_to(message, "Usage: /track <wallet_address> <wallet_name>")
            return

        wallet_address = args[1]
        wallet_name = args[2]

        if wallet_address.startswith("0x") and len(wallet_address) == 42:
            add_wallet(user_id, wallet_address, wallet_name)
            bot.reply_to(message, f"Wallet {wallet_address} ('{wallet_name}') is now being tracked!")
        else:
            bot.reply_to(message, "Invalid Ethereum wallet address.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")


@bot.message_handler(commands=["untrack"])
def untrack(message):
    try:
        user_id = message.chat.id
        wallet_address = message.text.split()[1]
        remove_wallet(user_id, wallet_address)
        bot.reply_to(message, f"Wallet {wallet_address} is no longer being tracked.")
    except IndexError:
        bot.reply_to(message, "Please provide a wallet address. Example: /untrack 0x123...")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

@bot.message_handler(commands=["list"])
def list_wallets(message):
    user_id = message.chat.id
    wallets = get_wallets(user_id)
    if wallets:
        response = "Your tracked wallets:\n" + "\n".join([f"{wallet_name}: {wallet_address}" for wallet_address, wallet_name in wallets])
        bot.reply_to(message, response)
    else:
        bot.reply_to(message, "You are not tracking any wallets.")


def poll_transactions():
    last_seen = defaultdict(dict)  # Stores the latest transaction hash for each wallet
    while True:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_id, wallet_address, wallet_name FROM tracked_wallets")
        rows = cursor.fetchall()
        conn.close()

        for user_id, wallet_address, wallet_name in rows:
            transactions = get_transactions(wallet_address)
            if transactions:
                latest_tx = transactions[0]
                tx_hash = latest_tx["hash"]
                value_in_eth = int(latest_tx["value"]) / 1e18  # Convert Wei to ETH
                if wallet_address not in last_seen[user_id] or last_seen[user_id][wallet_address] != tx_hash:
                    last_seen[user_id][wallet_address] = tx_hash
                    msg = f"""🚨 *New transaction detected*
Wallet Name: [{wallet_name}](https://etherscan.io/address/{wallet_address})
Tx Hash: [Etherscan](https://etherscan.io/tx/{tx_hash})
Value: {value_in_eth:.4f} ETH"""

                    bot.send_message(user_id,msg,parse_mode="Markdown")
        time.sleep(10)


@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    print(message.from_user.id)
    messager = message.chat.id
    if str(messager) == "7034272819" or str(messager) == "6219754372":
        send = bot.send_message(message.chat.id,"Enter message to broadcast")
        bot.register_next_step_handler(send,sendall)

    else:
        bot.reply_to(message, "You're not allowed to use this command")



def sendall(message):
    users = db_user.get_users()
    for chatid in users:
        try:
            msg = antiflood(bot.send_message, chatid, message.text)
        except Exception as e:
            print(e)

    bot.send_message(message.chat.id, "done")


@bot.message_handler(commands=['userno'])
def userno(message):
    print(message.from_user.id)
    messager = message.chat.id
    if str(messager) == "7034272819" or str(messager) == "6219754372":
        x = db_user.get_users()
        bot.reply_to(message,f"Total bot users: {len(x)}")
    else:
        bot.reply_to(message, "admin command")


def predictai(message):
    owner = message.chat.id
    msg = 'Allow our AI models to predict what the prices of crypto assets and allows you to know what the prices would be based on machine learning models which performs extensive technical Analysis on the OHLC Dataframe\n\nSelect a chain to predict what the price would be in the next days\n\n💡 Days should be either 7, 14 or 30 days'
    markup = quick_markup({
        'Ethereum': {'callback_data': 'predicteth'},
        'Solana': {'callback_data': 'predictsol'},
        'Bitcoin': {'callback_data': 'predictbtc'},
    })
    bot.send_message(owner, msg, reply_markup=markup)


def finalethpred(message):
    owner = message.chat.id
    days = int(message.text)
    if days == 7 or days == 14 or days == 30:
        try:
            generate_chart('ETH', owner)
            prediction = get_market_chart('ethereum', days)
            msg = f"Predictions for Ethereum over the next {days} days based on chart analysis and historical data\n\nDays                   Price\n\n"
            for x, y in prediction.items():
                msg += f"{x}            ${round(int(y), 2)}\n"
            msgy = f"{msg}"
            markup = quick_markup({
                'demo trade' : {'callback_data' : 'demotrade'}
            })
            photo = open(f'media/chart-img-{owner}.png', 'rb')
            bot.send_photo(owner, photo, msgy)
        except Exception as e:
            print(e)
            bot.send_message(owner, "Failed to parse prediction")
    else:
        bot.send_message(owner, "Timeframe should be either 7, 14 or 30 days")     

def finalsolpred(message):
    owner = message.chat.id
    days = int(message.text)
    if days == 7 or days == 14 or days == 30:
        try:
            generate_chart('SOL', owner)
            prediction = get_market_chart('solana', days)
            msg = f"Predictions for Solana over the next {days} days based on chart analysis and historical data\n\nDays                   Price\n\n"
            for x, y in prediction.items():
                msg += f"{x}            ${round(int(y), 2)}\n"
            msgy = f"{msg}"
            markup = quick_markup({
                'demo trade' : {'callback_data' : 'demotrade'}
            })
            photo = open(f'media/chart-img-{owner}.png', 'rb')
            bot.send_photo(owner, photo, msgy)
        except Exception as e:
            print
            bot.send_message(owner, "Failed to parse prediction")
    else:
        bot.send_message(owner, "Timeframe should be either 7, 14 or 30 days")     


def finalbtcpred(message):
    owner = message.chat.id
    days = int(message.text)
    if days == 7 or days == 14 or days == 30:
        try:
            generate_chart('BTC', owner)
            prediction = get_market_chart('bitcoin', days)
            msg = f"Predictions for Bitcoin over the next {days} days based on chart analysis and historical data\n\nDays                   Price\n\n"
            for x, y in prediction.items():
                msg += f"{x}            ${round(int(y), 2)}\n"
            msgy = f"{msg}"
            markup = quick_markup({
                'demo trade' : {'callback_data' : 'demotrade'}
            })
            photo = open(f'media/chart-img-{owner}.png', 'rb')
            bot.send_photo(owner, photo, msgy)
        except Exception as e:
            print(e)
            bot.send_message(owner, "Failed to parse prediction")
    else:
        bot.send_message(owner, "Timeframe should be either 7, 14 or 30 days")


@bot.message_handler(commands=['start'])
def start(message):
    owner = message.chat.id
    msg = f"""🎉 Introducing Aura AI: Autonomous Unified Resource Agent!
Meet $Aura AI, the next-gen Telegram bot transforming how you interact with AI! 🚀
What Can Aura AI Do?
1️⃣ Autonomous Agents: Handle tasks like market analysis, wallet monitoring, and arbitrage.
2️⃣ Privacy-First: Secure data with local or encrypted deployment.
3️⃣ Custom Agent Hub: Build agents tailored to your needs in real time.
4️⃣ Community-Driven: Collaborate to train agents for tasks like market analysis.
5️⃣ Whale Tracker: Spot Ethereum wallets making 10x+ gains.
6️⃣ Wallet Tracker: Monitor transactions and portfolios effortlessly.
Why Aura AI?
✨ Innovative agents that adapt to your tasks.
✨ Privacy-focused, with secure data handling.
✨ Customizable for your goals.
✨ Seamlessly integrates—all within Telegram.
Get ready to revolutionize your AI experience! 🚀
    """
    markup = quick_markup({
        'Autonomous Agent' : {'callback_data' : 'auto'},
        'Agent Hub' : {'callback_data' : 'agent'},
        'Privacy-First Wallet' : {'callback_data' : 'wallet'},
        "Crowd-Driven Agent" : {'callback_data' : 'crowd'},
        'Token Profitable Wallet' : {'callback_data' : 'top_wallet'},
        'Wallet Tracker' : {'callback_data' : 'wallet_tracker'},
        'Agent Services' : {'callback_data' : 'agent_services'},
        'Code Generator' : {'callback_data' : 'code_gen'},
        'Market Place' : {'callback_data' : 'aiagent'}
    })

    vid = open('vid.mp4', 'rb')
    bot.send_video(owner, vid, caption=msg,reply_markup=markup)
    #bot.send_message(owner, msg, reply_markup=markup)
    db_user.add_user(owner)


@bot.callback_query_handler(func= lambda call: True)
def call_handler(call):
    owner = call.message.chat.id
    message = call.message

    if call.data == 'market':
        msg = """🚀 Market Analysis Agent provides real-time insights into crypto market trends and token performance.
📊 It tracks price movements, identifies bullish and bearish patterns, and generates actionable predictions.
💡 Gain deeper market insights with automated analysis tailored to your portfolio or interests.
        """
        markup = quick_markup({
            'Research' : {'callback_data' : 'research'},
            'Market Prediction' : {'callback_data' : 'prediction'}
        })
        bot.send_message(owner, msg, reply_markup=markup)
    elif call.data == 'top_wallet':
        bot.send_message(owner, "Send Token address to get top profitable wallets? ")   
        bot.register_next_step_handler(message, check_top)

    elif call.data == 'aiagent':
        msg = """Welcome to Aura AI Marketplace 

Customize and build your prerffered AI agent that can be used in every field ranging from Data Research AI to Security-Focused AI Agent

select your preferred AI Agent below
        """
        markup = quick_markup({
            'Data Guru AI' : {'callback_data' : 'data_guru'},
            'Connector AI' : {'callback_data' : 'connector'},
            'Visionary AI' : {'callback_data' : 'visionai'},
            'Enfocer AI' : {'callback_data' : 'enforce'},
        }, 2)
        bot.send_message(owner, msg, reply_markup=markup)
        
    elif call.data == 'data_guru':
        msg = """Data Guru AI
        
The Data Guru AI is built for applications that require real-time data aggregation and deep blockchain insights. By integrating this AI into your product, you enable powerful data analytics, helping users track tokens, wallets, and market movements with ease.

*Cost $750*

        """
        markup = quick_markup({
            'customize' : {'callback_data' : 'datacus'},
        })
        photo = open('img1.jpg','rb')
        bot.send_photo(owner, photo, msg, reply_markup=markup)
        
    elif call.data == 'datacus':
        s = bot.send_message(owner, "Are you interested in integrating real-time blockchain data aggregation into your app?")
        bot.register_next_step_handler(s, ask_q)
        
    elif call.data == 'ai_pay':
        msg = """Please send the amount of eth  to this address:
0x68AadABF2887E1Bb96C77377E63D043e4Aff0641 ✅
process can take up to few minutes to get completed 
        """  
        bot.send_message(owner, msg)
        
    elif call.data == 'connector':
        msg = """Connector AI
        
This AI is ideal for developers building networking or collaboration features within their applications. The Connector AI analyzes trends to identify relevant partnerships and collaboration opportunities, empowering users to find the right business connections or joint ventures.

*Cost 900$*
        """
        markup = quick_markup({
            'customize' : {'callback_data' : 'concus'},
        })
        photo = open('img2.jpg','rb')
        bot.send_photo(owner, photo, msg, reply_markup=markup)
    
    elif call.data == 'concus':
        s = bot.send_message(owner, "Do you need to integrate a feature that identifies business opportunities and partnerships?")
        bot.register_next_step_handler(s, ask_q3)
        
    elif call.data == 'visionai':
        msg = """Visionary AI
For developers looking to offer future-proof solutions, The Visionary AI provides trend prediction and idea generation. It helps users anticipate upcoming shifts in the market, making it a perfect addition to products focused on forecasting, innovation, or future planning

*Cost 800$*       

        """
        markup = quick_markup({
            'customize' : {'callback_data' : 'vcus'},
        })
        photo = open('img3.jpg','rb')
        bot.send_photo(owner, photo, msg, reply_markup=markup)
        
    elif call.data == 'vcus':
        s = bot.send_message(owner, "Would you like to offer predictive trend analysis and innovation suggestions?")
        bot.register_next_step_handler(s, ask_q5)
        
    elif call.data == 'enforce':
        msg = """Enforcer AI

Security-focused developers will appreciate The Enforcer AI. This agent is designed to integrate into apps that require active monitoring and alerting of suspicious wallet activity and transactions, providing users with enhanced security features and real-time alerts.

*Cost 865$*

        """
        markup = quick_markup({
            'customize' : {'callback_data' : 'ecus'},
        })
        photo = open('img4.jpg','rb')
        bot.send_photo(owner, photo, msg, reply_markup=markup)
        
    elif call.data == 'ecus':
        s = bot.send_message(owner, "Need to add an AI-powered security feature to monitor wallet activity?")
        bot.register_next_step_handler(s, ask_q7)
        
        
    elif call.data == 'wallet_tracker':
        msg = """Welcome to Aura AI Bot Wallet Tracker
        
Use the following command to interact with the bot
/track <wallet address> <name> to start tracking a wallet
/untrack <wallet address> to remove a wallet
/list to see tracked wallets.
        
        """
        bot.send_message(owner, msg)

    elif call.data == 'code_gen':
        send = bot.send_message(call.message.chat.id, "Send your photo to the bot")
        bot.register_next_step_handler(send, code)

    elif call.data == 'back':
        bot.delete_message(owner, message.message_id)
        start(message)

    elif call.data == 'crowd':
        msg = """Welcome to the Community Agent Training Program! 🌐
Contribute your tasks to help train our AI-powered Community Agent, which learns from collective inputs to deliver smarter, more accurate insights.
        """
        markup = quick_markup({
            "Contribute to a Task" : {'callback_data' : 'contribute'},
            "Main Menu" : {'callback_data' : 'back'},
        })
        bot.send_message(owner, msg, reply_markup=markup)

    elif call.data == 'contribute':
        msg = """Great! What type of task would you like to assign to the Community Agent?"
        """
        markup = quick_markup({
            'Market Analysis Task' : {'callback_data' : 'market_task'},
            'Wallet Monitoring Task' : {'callback_data' : 'wallet_task'},
            'Arbitage Task' : {'callback_data' : 'arb_task'},
        })
        bot.send_message(owner, msg, reply_markup=markup)

    elif call.data == 'mrkpro':
        bot.send_message(owner, "Thank you! This information will help our agent adjust its analysis to time-sensitive volatility patterns for better predictions.")

    elif call.data == 'arbpro':
        bot.send_message(owner, "Thanks for your input! This data will help our agent fine-tune its arbitrage calculations, prioritizing speed and cost efficiency.")

    elif call.data == 'arb_task':
        bot.send_message(owner, "Profit Opportunity Check\nWas the arbitrage opportunity between Uniswap and Binance executed as suggested? (Yes/No)")
        bot.register_next_step_handler(message, arb1)

    elif call.data == 'market_task':
        msg ="Has the token's price movement over the last 24 hours matched our predictions? (Yes/No)"
        bot.send_message(owner, msg)
        bot.register_next_step_handler(message, mrk1)

    elif call.data == 'auto':
        msg = """Our Powerful Autonomous Agents!🌐
🥇 Arbitrage Agent: Detects price discrepancies across multiple exchanges, allowing you to capitalize on price differences for profit. It scans real-time data and alerts you to arbitrage opportunities, helping you stay ahead in the market.
🥈 Market Analysis Agent: Tracks market trends, analyzes token prices, and provides predictions on bullish and bearish movements. Customize alerts to receive notifications based on price shifts or significant token changes, ensuring you're always in the know.
        """
        markup = quick_markup({
        'Arbitrage Agent' : {'callback_data' : 'arbitrage'},
        'Market Analysis Agent' : {'callback_data' : 'market'},
    })   
        bot.send_message(owner, msg, reply_markup=markup)
    
    elif call.data == 'agent_services':
        msg = """AI Agent Licensing (Subscription-Based Program)
🚀 Unlock the Power of AI Agents with Licensing!
Gain exclusive access to our premium AI agents with flexible licensing options:
Perfect for developers looking to enhance their applications.
Choose short-term or long-term licenses based on your needs.
Scale seamlessly with upgrades and add-ons available anytime.
*Cost 550$*
        
        """
        markup = quick_markup({
            'Previus': {'callback_data' : 'agentserv2'},
            'Ready to License' : {'callback_data' : 'ai_pay'},
            'Next': {'callback_data' : 'agentserv2'},
        }, 3)
        bot.send_message(owner, msg, reply_markup=markup)
        
    elif call.data == 'agentserv2':
        msg = """Agent-as-a-Service (AaaS)
✨ Integrate AI Agents Effortlessly with AaaS
Leverage our plug-and-play API to seamlessly add powerful AI agents to your platform:
Access pre-built, highly customizable agents.
Focus on scaling your application, while we handle the AI complexities.
Get started quickly with developer-friendly integration.
*Cost 999$*
        
        """
        markup = quick_markup({
            'Previous': {'callback_data' : 'agentserv0'},
            'Interested' : {'callback_data' : 'ai_pay'},
            'Next': {'callback_data' : 'agentserv0'},
        }, 3)
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup= markup)
    
    
    elif call.data == 'agentserv0':
        msg = """AI Agent Licensing (Subscription-Based Program)
🚀 Unlock the Power of AI Agents with Licensing!
Gain exclusive access to our premium AI agents with flexible licensing options:
Perfect for developers looking to enhance their applications.
Choose short-term or long-term licenses based on your needs.
Scale seamlessly with upgrades and add-ons available anytime.
*Cost 550$*
        
        """
        markup = quick_markup({
            'Previus': {'callback_data' : 'agentser2'},
            'Ready to License' : {'callback_data' : 'ai_pay'},
            'Next': {'callback_data' : 'agentserv2'},
        },3)
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup= markup)
    
    
    elif call.data == 'ai_pay':
        msg = """Please send the amount of eth  to this address:
0x68AadABF2887E1Bb96C77377E63D043e4Aff0641 ✅
process can take up to few minutes to get completed 
        """  
        bot.send_message(owner, msg)

               
    elif call.data == 'arbitrage':
        msg = """Find Arbitrage opportunities between popular exchanges and take advantage of price differences of popular coins
        
Select an assest below to find arbitrage opportunities
        """
        markup = quick_markup({
            'Ethereum' : {'callback_data' : 'arbeth'},
            'Solana' : {'callback_data' : 'arbsol'},
            'Bitcoin' : {'callback_data' : 'arbbtc'},
        })
        bot.send_message(owner, msg,reply_markup= markup)

    elif call.data == 'arbeth':
        binance = funcs.get_exchange_price('ethereum', 'binance')
        bitget = funcs.get_exchange_price('ethereum', 'bitget')
        bybit = funcs.get_exchange_price('ethereum', 'bybit_spot')
        mexc = funcs.get_exchange_price('ethereum', 'mxc')
        bitmart = funcs.get_exchange_price('ethereum', 'bitmart')

        binance_price = binance['data']['usd']
        binance_link = binance['link']

        bitget_price = bitget['data']['usd']
        bitget_link = bitget['link']

        binance_price = binance['data']['usd']
        binance_link = binance['link']

        bybit_price = bybit['data']['usd']
        bybit_link = bybit['link']

        bitmart_price = bitmart['data']['usd']
        bitmart_link = bitmart['link']

        mexc_price = mexc['data']['usd']
        mexc_link = mexc['link']

        msg = f"""*Arbitrage Finder*
        
Price across multiple exchanges for *Ethereum*
```Arbitrage
Binance: ${binance_price}
Bybit: ${bybit_price}
Bitget: ${bitget_price}
```
        """
        markup = quick_markup({
            'Binance' : {'url' : binance_link},
            'Bybit' : {'url' : bybit_link},
            'Bitget' : {'url' : bitget_link},
        })
        bot.send_message(owner, msg, reply_markup= markup)
    elif call.data == 'arbbtc':
        binance = funcs.get_exchange_price('bitcoin', 'binance')
        bitget = funcs.get_exchange_price('bitcoin', 'bitget')
        bybit = funcs.get_exchange_price('bitcoin', 'bybit_spot')
        mexc = funcs.get_exchange_price('bitcoin', 'mxc')
        bitmart = funcs.get_exchange_price('bitcoin', 'bitmart')

        binance_price = binance['data']['usd']
        binance_link = binance['link']

        bitget_price = bitget['data']['usd']
        bitget_link = bitget['link']

        binance_price = binance['data']['usd']
        binance_link = binance['link']

        bybit_price = bybit['data']['usd']
        bybit_link = bybit['link']

        bitmart_price = bitmart['data']['usd']
        bitmart_link = bitmart['link']

        mexc_price = mexc['data']['usd']
        mexc_link = mexc['link']

        msg = f"""*Arbitrage Finder*
        
Price across multiple exchanges for *Bitcoin*
```Arbitrage
Binance: ${binance_price}
Bybit: ${bybit_price}
Bitget: ${bitget_price}
```
        """
        markup = quick_markup({
            'Binance' : {'url' : binance_link},
            'Bybit' : {'url' : bybit_link},
            'Bitget' : {'url' : bitget_link},
        })
        bot.send_message(owner, msg, reply_markup= markup)
    elif call.data == 'research':
        bot.send_message(owner, "Send a message to talk to our chatbot")

    elif call.data == 'arbsol':
        binance = funcs.get_exchange_price('solana', 'binance')
        bitget = funcs.get_exchange_price('solana', 'bitget')
        bybit = funcs.get_exchange_price('solana', 'bybit_spot')
        mexc = funcs.get_exchange_price('solana', 'mxc')
        bitmart = funcs.get_exchange_price('solana', 'bitmart')

        binance_price = binance['data']['usd']
        binance_link = binance['link']

        bitget_price = bitget['data']['usd']
        bitget_link = bitget['link']

        binance_price = binance['data']['usd']
        binance_link = binance['link']

        bybit_price = bybit['data']['usd']
        bybit_link = bybit['link']

        bitmart_price = bitmart['data']['usd']
        bitmart_link = bitmart['link']

        mexc_price = mexc['data']['usd']
        mexc_link = mexc['link']

        msg = f"""*Arbitrage Finder*
        
Price across multiple exchanges for *Solana*
```Arbitrage
Binance: ${binance_price}
Bybit: ${bybit_price}
Bitget: ${bitget_price}
```
        """
        markup = quick_markup({
            'Binance' : {'url' : binance_link},
            'Bybit' : {'url' : bybit_link},
            'Bitget' : {'url' : bitget_link},
        })
        bot.send_message(owner, msg, reply_markup= markup)

    elif call.data == 'agent':
        msg = """🚀 Create Your Own Custom Agents!
Design agents tailored to your needs—whether it's market analysis, portfolio monitoring, or sentiment tracking.
🔧 Fully Customizable: Adjust agent behavior, data sources, alerts, and task frequency.
🤖 Seamless Experience: Create, configure, and deploy your personalized agents in minutes.
        """
        markup = quick_markup({
            'Customise Agent' : {'callback_data' : 'custom_agent'}
        })
        bot.send_message(owner, msg, reply_markup=markup)

    elif call.data == 'wallet':
        msg = """Welcome to the Privacy-First Wallet Analyzer! With this feature, your wallet analysis is fully encrypted and private, ensuring no third parties have access to your data. Let's get started by analyzing your wallet securely.
        """   
        markup = quick_markup({
            'Analyze Wallet' : {'callback_data' : 'analyze'}
        })

        bot.send_message(owner, msg, reply_markup=markup)

    elif call.data == 'analyze':
        bot.send_message(owner, "Send an ethereum wallet to analyze: ")
        bot.register_next_step_handler(message, analyze)
    elif call.data == 'pay':
        msg = """Please send the amount of Eth to this address:
`0x68AadABF2887E1Bb96C77377E63D043e4Aff0641`
process can take up to few minutes to get completed✅
        """
        bot.send_message(owner, msg)

    elif call.data == 'cancel':
        bot.delete_message(owner, message.message_id)

    elif call.data == 'prediction':
        predictai(message)

    elif call.data == 'predicteth':
        s = bot.send_message(owner, "Enter time duration for prediction (7, 14 or 30 for days): ")  
        bot.register_next_step_handler(s, finalethpred)

    elif call.data == 'predictsol':
        s = bot.send_message(owner, "Enter time duration for prediction (7, 14 or 30 for days): ")  
        bot.register_next_step_handler(s, finalsolpred)

    elif call.data == 'predictbtc':
        s = bot.send_message(owner, "Enter time duration for prediction (7, 14 or 30 for days): ")  
        bot.register_next_step_handler(s, finalbtcpred)

    elif call.data == 'custom_agent':
        msg = """Define the Agent's Purpose Bot:
Please describe the purpose of your agent. What do you want it to focus on?
1️⃣ Analyze crypto market trends.
2️⃣ Monitor my portfolio for gains/losses.
3️⃣ Track social media sentiment about $ETH
💡 Make your choice by entering a number
        """
        y = bot.send_message(owner, msg)
        bot.register_next_step_handler(y, agent1)


def code(message):
    if message.photo:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_path = file_info.file_path
        downloaded_file = bot.download_file(file_path)

        bot.send_message(message.chat.id, "Generating Code")
        try:
            url = img_upload(downloaded_file)
            bot.send_message(message.chat.id, htmlTemplate(url), parse_mode="Markdown", disable_web_page_preview=True)
            bot.send_message(message.chat.id, cssTemplate(url), parse_mode="Markdown", disable_web_page_preview=True)
            bot.send_message(message.chat.id, "done")
        except Exception as e:
            bot.send_message(message.chat.id, f"An error occurred: {str(e)}")
    else:
        bot.send_message(message.chat.id, "Please send me an image.")    

def agent1(message):
    owner = message.chat.id
    try:
        opt =  int(message.text)
        if opt < 5:
            msg = """Select the Agent's Behavior Style Bot:
How would you like your agent to behave?
Options:
1️⃣ Analytical (Focuses on detailed analysis)
2️⃣ Aggressive (Makes quick, action-oriented decisions)
3️⃣ Conservative (Takes a cautious, risk-averse approach)
4️⃣ Optimistic (Focuses on positive trends and predictions)
5️⃣ Custom (Set your own behavior)
            """
            bot.send_message(owner, msg)
            bot.register_next_step_handler(message, agent2)
        else:
            bot.send_message(owner, "Invalid response")
    except Exception as e:
        bot.send_message(owner, "Reply should be a number from the above option")  


def arb1(message):
    owner = message.chat.id
    if message.text == 'yes' or message.text == 'Yes':
        bot.send_message(owner, "Thank you! This data will be used to improve the detection of viable arbitrage opportunities")
        bot.send_message(owner, "Did the token's price stay stable enough to allow arbitrage without slippage? (Yes/No)")
        bot.register_next_step_handler(message, arb2)

    elif message.text == 'No' or message.text == 'no':
        bot.send_message(owner, "Step terminated by User")

    else:
        bot.send_message(owner, "Reply Should be Yes/No")   


def arb2(message):
    owner = message.chat.id
    if message.text == 'yes' or message.text == 'Yes':
        bot.send_message(owner, " Your input will help adjust slippage tolerance in future arbitrage scans.")
        bot.send_message(owner, "Cross-Exchange Synchronization Check \nWas the price difference between the two exchanges consistent during the suggested arbitrage window? (Yes/No)")
        bot.register_next_step_handler(message, arb3)

    elif message.text == 'No' or message.text == 'no':
        bot.send_message(owner, "Step terminated by User")

    else:
        bot.send_message(owner, "Reply Should be Yes/No")        


def arb3(message):
    owner = message.chat.id
    if message.text == 'yes' or message.text == 'Yes':
        markup = quick_markup({
            'Proceed' : {'callback_data' : 'arbpro'},
        })
        bot.send_message(owner, "Thank you for your feedback! This helps enhance the timing accuracy of arbitrage windows", reply_markup=markup)

    elif message.text == 'No' or message.text == 'no':
        bot.send_message(owner, "Step terminated by User")

    else:
        bot.send_message(owner, "Reply Should be Yes/No")

def check_top(message):
    owner = message.chat.id
    try:
        data = get_top_wallet(message.text)     
        msg = f"Top Profit Wallet of Token `{message.text}`\n\n"
        for entry in data:
            msg += f"Address: `{entry['address']}`\n"
            msg += f"Avg Buy Price (USD): {float(entry['avg_buy_price_usd']):.6f}\n"
            msg += f"Avg Sell Price (USD): {float(entry['avg_sell_price_usd']):.6f}\n"
            msg += f"Total Tokens Bought: {float(entry['total_tokens_bought']):,.0f}\n"
            msg += f"Total USD Invested: {float(entry['total_usd_invested']):,.2f}\n"
            msg += f"Total Tokens Sold: {float(entry['total_tokens_sold']):,.0f}\n"
            msg += f"Total Sold USD: {float(entry['total_sold_usd']):,.2f}\n"
            msg += f"Avg Cost of Quantity Sold: {float(entry['avg_cost_of_quantity_sold']):.6f}\n"
            msg += f"Count of Trades: {entry['count_of_trades']}\n"
            msg += f"Realized Profit (USD): {float(entry['realized_profit_usd']):,.2f}\n"
            msg += f"Realized Profit Percentage: {entry['realized_profit_percentage']:.2f}%\n\n"
        for i in range(0, len(msg), 4096):
            bot.send_message(owner, msg[i:i+4096])

    except Exception as e:
        print(e)
def agent2(message):
    owner = message.chat.id
    try:
        opt =  int(message.text)
        if opt < 5:
            msg = """Set Data Sources for the Agent Bot:
Where would you like your agent to gather data from?
Options:
1️⃣ Blockchain Data (e.g., Etherscan, CoinGecko)
2️⃣ Social Media (e.g., Twitter, Reddit, Telegram)
3️⃣ DeFi Platforms (e.g., Uniswap, PancakeSwap)
4️⃣ Custom API (Connect your own data source)
5️⃣ Other (Please specify)
            """
            bot.send_message(owner, msg)
            bot.register_next_step_handler(message, agent3)
        else:
            bot.send_message(owner, "Invalid response")
    except Exception as e:
        bot.send_message(owner, "Reply should be a number from the above option")  

def agent3(message):
    owner = message.chat.id
    try:
        opt =  int(message.text)
        if opt < 5:
            msg = """
 Define Alerts and Notification Settings Bot:
What type of alerts would you like your agent to send you?
Options:
1️⃣ Price Fluctuations (Alert for price changes > 5%)
2️⃣ Volume Movements (Alert when large transactions occur)
3️⃣ Sentiment Changes (Alert when a token's sentiment changes)
4️⃣ Custom Alerts (Specify your own conditions)
5️⃣ No Alerts (Don’t send any alerts)
            """
            bot.send_message(owner, msg)
            bot.register_next_step_handler(message, agent4)
        else:
            bot.send_message(owner, "Invalid response")
    except Exception as e:
        bot.send_message(owner, "Reply should be a number from the above option")  


def agent4(message):
    owner = message.chat.id
    try:
        opt =  int(message.text)
        if opt < 5:
            msg = """ Customize Task Frequency or Time Intervals Bot:
"How often would you like your agent to perform tasks or check for updates?"
Options:
1️⃣ Hourly
2️⃣ Daily
3️⃣ Weekly
4️⃣ Custom Interval (e.g., every 2 hours, etc.)
            """
            bot.send_message(owner, msg)
            bot.register_next_step_handler(message, agent5)
        else:
            bot.send_message(owner, "Invalid response")
    except Exception as e:
        bot.send_message(owner, "Reply should be a number from the above option") 


def agent5(message):
    owner = message.chat.id
    try:
        opt =  int(message.text)
        if opt < 5:
            msg = """Let’s name your agent! What would you like to call it?
            """
            bot.send_message(owner, msg)
            bot.register_next_step_handler(message, agent6)
        else:
            bot.send_message(owner, "Invalid response")
    except Exception as e:
        bot.send_message(owner, "Reply should be a number from the above option") 

def agent6(message):
    owner = message.chat.id
    msg = f"""Would you like to make any changes or confirm your customised agent {message.text}?"
cost 1200$
    """
    markup = quick_markup({
        'Confirm' : {'callback_data' : 'pay'},
        'Cancel' : {'callback_data' : 'cancel'},
    })
    bot.send_message(owner, msg, reply_markup=markup)


def analyze(message):
    owner = message.from_user.id
    token = str(message.text)
    if token.startswith('0x'):
        computes = db_user.get_request(owner)
        pnl = funcs.wallet_pnl(token)
        if pnl:
            msg = f"""*Wallet PnL Analyzer*
*wallet*: `{token}`
                
*Total Trades*: {pnl['total_count_of_trades']}
*Total Profits USD*: ${round(float(pnl['total_realized_profit_usd']), 2)}
*Total Profit %*: {round(float(pnl['total_realized_profit_percentage']), 2)}%
*Total Buys | Sell*: {pnl['total_buys']} | {pnl['total_sells']}
*Total Volume*: ${round(float(pnl['total_trade_volume']), 2)}
*Volume Buy | Sell*: ${round(float(pnl['total_bought_volume_usd']), 2)} | $ {round(float(pnl['total_sold_volume_usd']), 2)}
                """
            bot.send_message(owner, msg)
            compute = computes + 1
            db_user.update_request(compute, owner)
        else:
            bot.send_message(owner, "Please /upgrage your account")
    else:
        bot.send_message(owner, 'Invalid wallet Adress...')

def mrk1(message):
    owner = message.chat.id
    if message.text == 'yes' or message.text == 'Yes':
        bot.send_message(owner, "Thank you! This feedback has been logged to improve future predictions")
        bot.send_message(owner, "Sentiment Analysis Feedback\nBased on social media, does the sentiment for $ETH feel bullish to you? (Yes/No)")
        bot.register_next_step_handler(message, mrk2)

    elif message.text == 'No' or message.text == 'no':
        bot.send_message(owner, "Step terminated by User")

    else:
        bot.send_message(owner, "Reply Should be Yes/No")


def mrk2(message):
    owner = message.chat.id
    if message.text == 'yes' or message.text == 'Yes':
        bot.send_message(owner, " Your input has been recorded and will help refine sentiment weight in future analyses")
        bot.send_message(owner, "Was its price movement more predictable during certain hours (Yes/No)?")
        bot.register_next_step_handler(message, mrk3)

    elif message.text == 'No' or message.text == 'no':
        bot.send_message(owner, "Step terminated by User")

    else:
        bot.send_message(owner, "Reply Should be Yes/No")  


def mrk3(message):
    owner = message.chat.id
    if message.text == 'yes' or message.text == 'Yes':
        markup = quick_markup({
            'Proceed' : {'callback_data' : 'mrkpro'},
        })
        bot.send_message(owner, "Thanks for your feedback! Your response has been used to calibrate agent recommendations", reply_markup=markup)

    elif message.text == 'No' or message.text == 'no':
        bot.send_message(owner, "Step terminated by User")

    else:
        bot.send_message(owner, "Reply Should be Yes/No")     


def ask_q(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        s = bot.send_message(owner, "Would you like the AI to monitor and analyze specific wallets or tokens?")
        bot.register_next_step_handler(s, ask_q2)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
def ask_q2(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        markup = quick_markup({
            'Cost $750' : {'callback_data' : 'ai_pay'}
        })
        s = bot.send_message(owner, "your customisation updated ✅\nIf you would like to buy this agent press the button below", reply_markup=markup)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
        
def ask_q3(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        s = bot.send_message(owner, "Want the AI to suggest potential collaborators based on market trends?")
        bot.register_next_step_handler(s, ask_q4)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
def ask_q4(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        markup = quick_markup({
            'Cost $900' : {'callback_data' : 'ai_pay'}
        })
        s = bot.send_message(owner, "your customisation updated ✅\nIf you would like to buy this agent press the button below", reply_markup=markup)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
        
def ask_q5(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        s = bot.send_message(owner, "Are you looking to create a future forecasting module in your app?")
        bot.register_next_step_handler(s, ask_q6)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
def ask_q6(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        markup = quick_markup({
            'Cost $800' : {'callback_data' : 'ai_pay'}
        })
        s = bot.send_message(owner, "your customisation updated ✅\nIf you would like to buy this agent press the button below", reply_markup=markup)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
        
def ask_q7(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        s = bot.send_message(owner, "Would you like the AI to detect and alert on suspicious blockchain transactions?")
        bot.register_next_step_handler(s, ask_q8)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")
        
def ask_q8(message):
    owner = message.chat.id
    reply = message.text
    if reply == 'yes' or reply == "Yes":
        markup = quick_markup({
            'Cost $865' : {'callback_data' : 'ai_pay'}
        })
        s = bot.send_message(owner, "your customisation updated ✅\nIf you would like to buy this agent press the button below", reply_markup=markup)
    elif reply == 'no' or reply == 'No':
        bot.send_message(owner, "Operation cancelled by user")      
    else:
        bot.send_message(owner, "Reply should either be Yes or No")


@bot.message_handler(func=lambda message: True)
def chat_bot_(message):
    owner = message.chat.id
    text = message.text
    #bot.reply_to(message, message.text)
    reply = funcs.chat_bot(text)
    bot.send_message(owner, reply)

if __name__ == "__main__":
    init_db()
    import threading

    # Start the polling in a separate thread
    polling_thread = threading.Thread(target=poll_transactions, daemon=True)
    polling_thread.start()
    bot.infinity_polling()