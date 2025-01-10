import requests
import os
from dotenv import load_dotenv
from moralis import evm_api
import openai
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import numpy as np
import json
from datetime import timedelta
from datetime import datetime, timedelta
from moralis import evm_api
import time

load_dotenv()

api_key = os.getenv('COINGECKO')

moralis_api_key = os.getenv('MORALIS')

openai_api_key = os.getenv('OPENAI')


def chat_bot(prompt):
    openai.api_key = openai_api_key
    
    messages = [
        {
            'role' : 'system',
            'content' : "you are a crypto assistant only and you only answer talk about crypto currency,  Large-scale data Calculations and Decentralized transaction analysis"
        }
    ]
    
    if prompt:
        messages.append(
            {
                "role" : "user",
                "content" : prompt
            },
        )
        
        chat = openai.chat.completions.create(model='gpt-4o-mini', messages=messages)
        
        reply = chat.choices[0].message.content
        
        #print(reply)
        
        messages.append(
            {
                "role" : "assistant",
                "content" : reply
            }
        )
        
        return reply

def get_exchange_price(coin_id: str, exchange: str) -> dict:
    """Needed Exchanges 
    
    binance
    
    bitget
    
    bitmart
    
    bybit_spot
    
    mxc - Mexc
    
    coin_id {
        bitcoin
        ethereum
        solana
        
        future chains could be added later
    }
    
    """
    url = f"https://pro-api.coingecko.com/api/v3/coins/{coin_id}/tickers?exchange_ids={exchange}&include_exchange_logo=false"

    headers = {
        "accept": "application/json",
        "x-cg-pro-api-key": api_key
    }

    response = requests.get(url, headers=headers).json()
    if exchange == 'binance':
        result = response['tickers'][1]['converted_last']
        link = response['tickers'][1]['trade_url']
        r_dict = {
            'data' : result,
            'link' : link
        }
        return r_dict
    else:
        result = response['tickers'][1]['converted_last']
        link = response['tickers'][1]['trade_url']
        r_dict = {
            'data' : result,
            'link' : link
        }
        return r_dict
    
def wallet_pnl(address: str):
    params = {
        "chain": "eth",
        "address": address
    }
    result = evm_api.wallets.get_wallet_profitability_summary(
        api_key= moralis_api_key,
        params=params,
    )
    return result


def get_market_chart(coin_id: str = "bitcoin",preday = 7, days: int = 30):
    
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": str(days)
    }
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": "CG-PoMurepErqHySZn6VjNbxvND"  # Updated headers with API key
    }
    response = requests.get(url, params=params, headers=headers)
    
    # Check for errors
    if response.status_code != 200:
        raise Exception(f"Error fetching data: {response.status_code} - {response.text}")
    
    data = response.json()
    
    # Parse OHLC data
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')  # Convert timestamp
    
    pre = predict_future_prices(df, preday)
    return pre

def predict_future_prices(df: pd.DataFrame, days_to_predict: int):
    """
    Predict future prices for a given number of days.
    Args:
        df (pd.DataFrame): DataFrame with historical OHLC prices.
        days_to_predict (int): Number of days to predict.
    Returns:
        dict: Predicted prices with dates as keys and prices as values.
    """
    # Use only 'close' price for prediction
    df['close_shifted'] = df['close'].shift(-1)
    df.dropna(inplace=True)

    X = df[['close']]  # Ensure X is always a DataFrame with column names
    y = df['close_shifted']

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Train model
    model = RandomForestRegressor(random_state=42)
    model.fit(X_train, y_train)

    # Evaluate the model (optional)
    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"Model RMSE: {rmse}")

    # Multi-day prediction
    predictions = {}
    last_date = df['timestamp'].iloc[-1]  # Get the last available date
    current_input = pd.DataFrame([X.iloc[-1].values], columns=['close'])  # Wrap the input in a DataFrame

    for i in range(days_to_predict):
        next_prediction = model.predict(current_input)[0]
        next_date = last_date + timedelta(days=i + 1)  # Increment date
        predictions[next_date.strftime('%Y-%m-%d')] = next_prediction
        current_input = pd.DataFrame([[next_prediction]], columns=['close'])  # Update input as DataFrame

    return predictions


def generate_chart(symbol: str, userid: int):
    headers = {
        'x-api-key': 'vnDrOf3wlruCCHf4b0jy8hcdqwYzjHc5MBQww6Ad',
        'content-type': 'application/json',
    }

    json_data = {
        'theme': 'dark',
        'symbol': f'BINANCE:{symbol}USDT',
    }

    response = requests.post('https://api.chart-img.com/v2/tradingview/advanced-chart', headers=headers, json=json_data)

    with open(f'media/chart-img-{userid}.png', 'wb') as f:
        f.write(response.content)

def get_top_wallet(address):
    params = {
    "chain": "eth",
    "address": "0x309850e0F7d5191B708eBaC76b14161dC3046385"
    }

    result = evm_api.token.get_top_profitable_wallet_per_token(
    api_key= moralis_api_key,
    params=params,
    )

    data = result['result'][:10]
    return data

