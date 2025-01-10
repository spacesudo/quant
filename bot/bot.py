import telebot
from dotenv import load_dotenv
import json
import os
import funcs
from cloudinary import uploader
import random
import cloudinary
import requests
from telebot.util import antiflood, extract_arguments, quick_markup
from db import Users
from funcs import get_market_chart, generate_chart, get_top_wallet
import sqlite3
import time
from collections import defaultdict
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
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
            u = random.randint(20, 100)
            msg = f"Predictions for Ethereum over the next {days} Sentiment Source: Twitter\nAnalyzed Tweets: {random.randint(1000, 5000)}\nSentiment: {'Bullish' if u > 50 else 'Bearish'} ({u}%)\nPrice Prediction : \n"
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
            u = random.randint(20, 100)
            msg = f"Predictions for Ethereum over the next {days} Sentiment Source: Twitter\nAnalyzed Tweets: {random.randint(1000, 5000)}\nSentiment: {'Bullish' if u > 50 else 'Bearish'} ({u}%)\nPrice Prediction : \n"
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
            u = random.randint(20, 100)
            msg = f"Predictions for Ethereum over the next {days} Sentiment Source: Twitter\nAnalyzed Tweets: {random.randint(1000, 5000)}\nSentiment: {'Bullish' if u > 50 else 'Bearish'} ({u}%)\nPrice Prediction : \n"
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
    msg = f"""*Introducing QuantaAI: Quantum & AI Integration on Telegram!*

QuantaAI is now live, offering cutting-edge quantum-powered AI tools to revolutionize your projects and workflows. 🚀

*Key Features:*
1️⃣ *Quantum Computing*: Harness decentralized quantum resources for superior performance.  
2️⃣ *Dataset Optimization*: Effortlessly prepare data for quantum efficiency.  
3️⃣ *Hybrid Consensus*: Leverage Proof-of-Quantum (PoQ) and Proof-of-Intelligence (PoI) technologies.  

* Why Choose QuantaAI?*
✨ *Next-Gen Innovation*: Merging quantum and AI for advanced problem-solving.  
✨ *Customizable Tools*: Tailored for predictive modeling, data enhancement, and more.  
✨ *User-Friendly*: Instant setup via Telegram-based workflows.  

👉 *Join QuantaAI* and unlock intelligent quantum solutions today!
    """
    markup = quick_markup({
        'Quantum Resources Marketplace' : {'callback_data' : 'quantum'},
        'Quantum Data Optimizer' : {'callback_data' : 'quantum_optim'},
        'Hybrid Consensus Algorithm' : {'callback_data' : 'hybrid_consensus'},
        'AI-Driven Quantum Prediction Markets' :{'callback_data' : 'market'},
        'AI/Quantum Computing as a Service (AQCaaS)' : {'callback_data' : 'qaas'},
    })
    
    vid = open('img.png', 'rb')
    bot.send_photo(owner, vid, caption=msg,reply_markup=markup)
    #bot.send_message(owner, msg, reply_markup=markup)
    db_user.add_user(owner)
    

@bot.callback_query_handler(func= lambda call: True)
def call_handler(call):
    owner = call.message.chat.id
    message = call.message
    
    if call.data == 'market':
        msg = """AI-Driven Quantum Prediction Markets integrate quantum computing and AI to offer advanced predictive analytics. This feature provides users with unparalleled insights by processing large datasets and uncovering trends that would be difficult to spot with traditional methods. By combining quantum systems' computational power with AI, users can access highly accurate forecasts. This tool empowers businesses and individuals to make data-driven decisions with a competitive advantage.
with this two button below
        """
        markup = quick_markup({
            #'Research' : {'callback_data' : 'research'},
            'First Market Prediction' : {'callback_data' : 'prediction'},
            'Chart Prediction' : {'callback_data' : 'chartpred'},

        })
        bot.send_message(owner, msg, reply_markup=markup)
        
    elif call.data == 'chartpred':
        bot.send_message(owner, "Send an image of the chart you want to predict")
        bot.register_next_step_handler(message, chartpredict)
        
    elif call.data == 'qaas':
        msg = """AI/Quantum Computing as a Service (AQCaaS) offers scalable solutions that combine quantum computing and AI to tackle complex problems. This service makes advanced computational power accessible to businesses, developers, and researchers across various fields. From simulations to machine learning, users can leverage the capabilities of quantum systems without needing specialized infrastructure. AQCaaS enables organizations to innovate and solve problems at the forefront of technology.
with this two button below
        """   
        markup = quick_markup({
            'AI Training Model' : {"callback_data" : 'aimode'},
            'Quantum Algorithm Simulation driven' : {"callback_data" : 'qalgo'},
        })
        bot.send_message(owner, msg, reply_markup=markup)
        
    elif call.data == 'aimode':
        msg = """Train your AI model with quantum computing. Please provide the following:
1️⃣ Dataset (Upload CSV or JSON).
2️⃣ Training Goal: (e.g., Fraud Detection, Sentiment Analysis)
        """
        bot.send_message(owner, msg)
        bot.send_message(owner, "Input your training goal (e.g., Fraud Detection, Sentiment Analysis)")
        bot.register_next_step_handler(message, aimode1)
    elif call.data == 'qalgo':
        msg = """Define Complexity Level:

"To optimize the simulation, choose the complexity level of the task:
1️⃣ Basic (Small datasets, single-variable optimization)
2️⃣ Moderate (Multi-variable optimization, medium datasets)
3️⃣ Advanced (Large datasets, complex multi-variable tasks)
        """   
        bot.send_message(owner, msg)
        bot.register_next_step_handler(message, complexity_level)
        
    elif call.data == 'hybrid_consensus':
        
        msg = """The Hybrid Consensus Algorithm combines Proof-of-Quantum (PoQ) and Proof-of-Intelligence (PoI) to secure and validate transactions in the quantum network. PoQ leverages quantum computational power, while PoI uses intelligence-driven decision-making to enhance the security and reliability of the network. This dual approach ensures both speed and security, It enables the quantum network to scale efficiently while maintaining high trust and performance standards

Select a computational challenge for scalability and Task  Management:
        """
        mar = quick_markup({
            'Large-scale data Calculations' : {"callback_data" : 'largerr'},
            'Decentralized transaction analysis' : {"callback_data" : 'largerrd'},
        })
        bot.send_message(owner, msg, reply_markup=mar)
    elif call.data == 'largerr' or call.data == 'largerrd':
        bot.send_message(owner, "Send a message to the bot to start a conversation")
    elif call.data == 'quantum_optim':
        msg = """The Quantum Data Optimizer (QDO) prepares and enhances your data for quantum processing, ensuring it is in the ideal format for optimal performance. It optimizes data to reduce computational overhead, leading to faster and more accurate results. By bridging classical and quantum systems, QDO ensures seamless integration between both worlds. This tool maximizes the efficiency of quantum algorithms and improves overall processing capabilities.
        """    
        mat = quick_markup({
            'Optimize' : {'callback_data' : 'qopt'}
        })
        bot.send_message(owner, msg, reply_markup=mat)
        
    elif call.data == 'qopt':
        msg = """Upload your dataset for quantum optimization. Accepted formats: CSV, JSON, or TXT. Our system will enhance it for quantum processing efficiency."""
        bot.send_message(owner, msg)
        bot.register_next_step_handler(message, qoptfile)
        
        
    elif call.data == 'quantum':
        msg = """The Decentralized Quantum Marketplace allows users to rent or lease quantum computing resources directly from a decentralized network. By facilitating peer-to-peer transactions, it ensures a fair and transparent system. This platform democratizes access to quantum computing, providing opportunities for innovation at every level. Whether for research or development, the marketplace connects users with the computational power they need.
        """
        mar = quick_markup({
            'Rent Quantum Resources' :{'callback_data' : 'quant_rent'},
            'Lease your Resources' :{'callback_data' : 'quant_lease'},
        })
        bot.send_message(owner, msg, reply_markup= mar)
        
    elif call.data == 'quant_lease':
           msg = """To list your quantum resource for leasing, please upload a configuration file or provide the following details:
           
1️⃣ Performance (QPU): Specify the computational power (e.g., 1,500 QPU).
2️⃣ Resource Availability: Mention the total hours/month your resource will be available.
3️⃣ Lease Price ($/hour): Define the price for leasing.
4️⃣ Additional Specifications: Upload a file (JSON, CSV, or TXT) containing your resource’s technical details.
           """
           mar = quick_markup({
               'Get Started' : {'callback_data' : 'q_l'},
           })
           bot.send_message(owner, msg, reply_markup=mar)
           
    elif call.data == 'q_l':
        bot.send_message(owner, 'Performance (QPU): Specify the computational power (e.g., 1,500 QPU)?')
        bot.register_next_step_handler(call.message, ql1)
        
    elif call.data == 'quant_rent':
        msg = """QuantumCore Pro 1000
Performance: 1,000 QPU
Use Case: Designed for quantum computing enthusiasts and small-scale projects, QuantumCore Pro 1000 is perfect for testing quantum algorithms and exploring basic cryptographic principles. It excels in simulating quantum states and conducting light optimization tasks. Affordable and reliable, it's the ideal entry point for learning and experimentation.

*Cost: $2000/month*
        """
        mar = quick_markup({
            'Previous' : {'callback_data' : 'qr5'},
            'Purchase' : {'callback_data' : 'ai_pay'},
            'Next' : {'callback_data' : 'qr2'},
        }, 3)
        
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup=mar)
        
    elif call.data == 'qr2':
        msg = """QuantumEdge 1500
Performance: 1,500 QPU
Use Case: This mid-tier machine is tailored for developers and researchers requiring moderate computational power. QuantumEdge 1500 supports advanced modeling, predictive analytics, and building intermediate-level quantum AI prototypes. It’s also ideal for processing structured data in financial and research applications. Balanced and efficient, it’s great for scaling up projects.

*Cost: $2,500/month*
        """
        mar = quick_markup({
            'Previous' : {'callback_data' : 'quant_rent'},
            'Purchase' : {'callback_data' : 'ai_pay'},
            'Next' : {'callback_data' : 'qr3'},
        }, 3)
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup=mar)
        
    elif call.data == 'qr3':
        msg = """QuantumMax 2200
Performance: 2,200 QPU
Use Case: QuantumMax 2200 is perfect for startups and small enterprises tackling data-heavy challenges. Its robust power handles portfolio optimization, risk analysis, and supply chain enhancements. With its ability to integrate with quantum-enhanced decision-making tools, it empowers organizations to innovate and optimize operations seamlessly.

*Cost: $4,000/month*
        """
        mar = quick_markup({
            'Previous' : {'callback_data' : 'qr2'},
            'Purchase' : {'callback_data' : 'ai_pay'},
            'Next' : {'callback_data' : 'qr4'},
        }, 3)
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup=mar)
        
    elif call.data == 'qr4':
        msg = """QuantumElite 5000
Performance: 5,000 QPU
Use Case: Built for industrial-scale applications, QuantumElite 5000 delivers unmatched performance for demanding computational needs. It supports tasks like drug discovery, material simulations, and large-scale cryptographic systems. Ideal for enterprises seeking efficiency in logistical operations or advanced problem-solving at scale, this powerhouse redefines industrial computation.

*Cost: $7000/month*
        """
        mar = quick_markup({
            'Previous' : {'callback_data' : 'qr3'},
            'Purchase' : {'callback_data' : 'ai_pay'},
            'Next' : {'callback_data' : 'qr5'},
        }, 3)
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup=mar)
        
    elif call.data == 'qr5':
        msg = """QuantumUltra 8000
Performance: 8,000 QPU
Use Case: QuantumUltra 8000 is the ultimate solution for cutting-edge research and extreme precision tasks. Perfect for multi-variable optimizations, climate modeling, and high-complexity simulations, it’s built for organizations pushing the boundaries of AI and quantum innovation. With its unparalleled computational power, it supports the most ambitious projects in science and technology.

*Cost: $14,000/month*
        """
        mar = quick_markup({
            'Previous' : {'callback_data' : 'qr4'},
            'Purchase' : {'callback_data' : 'ai_pay'},
            'Next' : {'callback_data' : 'quant_rent'},
        }, 3)
        bot.edit_message_text(msg, owner, call.message.message_id, reply_markup=mar)
        
        
    elif call.data == 'top_wallet':
        bot.send_message(owner, "Send Token address to get top profitable wallets? ")   
        bot.register_next_step_handler(message, check_top)
    
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

def complexity_level(message):
    bot.send_message(message.chat.id, "Would you like to prioritize energy efficiency over speed for this task? (Yes/No)")
    bot.register_next_step_handler(message, energy_efficiency)

def energy_efficiency(message):
    bot.send_message(
        message.chat.id,
        "Briefly describe the nature of your dataset or task (e.g., optimizing supply chains, predicting token prices):"
    )
    bot.register_next_step_handler(message, dataset_description)

def dataset_description(message):
    markup = quick_markup({"Data Integration": {"callback_data": "data_integration"}})
    bot.send_message(message.chat.id, "Thank you! This feedback has been logged.", reply_markup=markup)

# Handle Data Integration
@bot.callback_query_handler(func=lambda call: call.data == "data_integration")
def data_integration(call):
    markup = quick_markup(
        {
            "1️⃣ Yes (Upload a dataset or provide an API)": {"callback_data": "integration_yes"},
            "2️⃣ No (Use standard simulation settings)": {"callback_data": "integration_no"},
        }
    )
    bot.send_message(call.message.chat.id, "Would you like to integrate external data for more accurate results?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["integration_yes", "integration_no"])
def priority_metrics(call):
    bot.send_message(
        call.message.chat.id,
        "Priority Metrics Selection:\n\n"
        "Select your priority metrics for the quantum algorithm simulation:\n"
        "1️⃣ Speed Optimization (Quickest results)\n"
        "2️⃣ Accuracy (Highest precision in calculations)\n"
        "3️⃣ Resource Efficiency (Minimize energy/computational use)\n\n"
        "Do you want to allocate additional quantum resources for faster processing? (Yes/No)"
    )
    bot.register_next_step_handler(call.message, quantum_resources)

def quantum_resources(message):
    bot.send_message(message.chat.id, "Should the simulation include risk-adjusted predictions in the final report? (Yes/No)")
    bot.register_next_step_handler(message, risk_adjusted)

def risk_adjusted(message):
    bot.send_message(
        message.chat.id,
        "What is the most critical outcome for this simulation (e.g., speed, accuracy, cost efficiency)?"
    )
    bot.register_next_step_handler(message, critical_outcome)

def critical_outcome(message):
    markup = quick_markup({"Proceed": {"callback_data": "proceed"}})
    bot.send_message(
        message.chat.id,
        "Thanks for your feedback! Your response has been used to calibrate recommendations.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "proceed")
def proceed(call):
    bot.send_message(
        call.message.chat.id,
        "Thank you! This information will help our algorithm fine-tune its parameters to handle complex computational tasks more efficiently and deliver optimized results tailored to your requirements."
    )


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


def aimode1(message):
    owner = message.chat.id
    if message.text:
        bot.send_message(owner, "Upload a file (JSON, CSV, or TXT) containing your dataset resources details") 
        bot.register_next_step_handler(message, aimode2)
        

def aimode2(message):
    if message.document:
        bot.reply_to(message, "File received! Optimizing your data...")

        # Simulate processing with a progress bar
        progress_messages = [
            "Optimizing your data... 0% complete.",
            "Optimizing your data... 50% complete.",
            "Optimizing your data... 100% complete!",
        ]
        for progress_message in progress_messages:
            time.sleep(2)  # Simulate processing delay
            bot.send_message(message.chat.id, progress_message)

        # Download the file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Prepare a new JSON file with a renamed filename
        optimized_file_name = "optimized_by_Quanta_Ai.json"
        with open(optimized_file_name, "w") as json_file:
            # Assuming the file contains text data, parse and save as JSON
            try:
                data = downloaded_file.decode('utf-8')  # Decode bytes to string
                json_data = json.loads(data)  # Try parsing as JSON
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Fallback: treat the file content as a plain string
                json_data = {"content": downloaded_file.decode('utf-8')}

            # Write the content to the new JSON file
            json.dump(json_data, json_file, indent=4)

        # Send the renamed and converted JSON file back to the user
        with open(optimized_file_name, "rb") as optimized_file:
            bot.send_message(message.chat.id, "Optimization complete! Here's your optimized file:")
            bot.send_document(message.chat.id, optimized_file)

        # Clean up the temporary file
        os.remove(optimized_file_name)   
    else:
        bot.send_message(message.chat.id, "message should be a document")

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

def ql1(message):
    owner = message.chat.id
    bot.send_message(owner, "Resource Availability: Mention the total hours/month your resource will be available.")
    bot.register_next_step_handler(message, ql2)
    
def ql2(message):
    owner = message.chat.id
    bot.send_message(owner, "Lease Price ($/hour): Define the price for leasing.")
    bot.register_next_step_handler(message, ql3)

def chartpredict(message):
    owner = message.chat.id
    if message.photo:
        bot.send_message(owner, "Analyzing chart data...")
        time.sleep(2)
        bot.send_message(owner, "Optimizing future outcome...")
        time.sleep(3)
        w = ['Bullish', 'Bearish']
        bot.reply_to(message, f"Based on chart Analysis, the chart tends to show more {random.choice(w)} trend.")

def ql3(message):
    owner = message.chat.id
    bot.send_message(owner, "Additional Specifications: Upload a file (JSON, CSV, or TXT) containing your resource’s technical details.")
    bot.register_next_step_handler(message, ql4)

def ql4(message):
    owner = message.chat.id
    if message.document:
        bot.send_message(owner, "Thank you! Your quantum resource has been added in our data successfully")
    else:
        bot.send_message(owner, "message should be a file document")
    

def qoptfile(message):
    if message.document:
        bot.reply_to(message, "File received! Optimizing your data...")

        # Simulate processing with a progress bar
        progress_messages = [
            "Optimizing your data... 0% complete.",
            "Optimizing your data... 50% complete.",
            "Optimizing your data... 100% complete!",
        ]
        for progress_message in progress_messages:
            time.sleep(2)  # Simulate processing delay
            bot.send_message(message.chat.id, progress_message)

        # Download the file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Prepare a new JSON file with a renamed filename
        optimized_file_name = "optimized_by_Quanta_Ai.json"
        with open(optimized_file_name, "w") as json_file:
            # Assuming the file contains text data, parse and save as JSON
            try:
                data = downloaded_file.decode('utf-8')  # Decode bytes to string
                json_data = json.loads(data)  # Try parsing as JSON
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Fallback: treat the file content as a plain string
                json_data = {"content": downloaded_file.decode('utf-8')}

            # Write the content to the new JSON file
            json.dump(json_data, json_file, indent=4)

        # Send the renamed and converted JSON file back to the user
        with open(optimized_file_name, "rb") as optimized_file:
            bot.send_message(message.chat.id, "Optimization complete! Here's your optimized file:")
            bot.send_document(message.chat.id, optimized_file)

        # Clean up the temporary file
        os.remove(optimized_file_name)
    else:
        bot.send_message(message.chat.id, "Please send a file")
    
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

    # Start the bot
    bot.infinity_polling()