import threading
#import telebot
import time
import sys
import os
import glob
import random
from telebot import TeleBot
from telebot import types
from dotenv import load_dotenv

load_dotenv(override=False)

# Токен только из окружения (никогда не хранить в коде). См. .env.example.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("Ошибка: задайте TELEGRAM_BOT_TOKEN в .env или в переменных окружения.")
    sys.exit(1)
bot = TeleBot(TOKEN)

def stop_bot():
    print("Press 'N' to stop the bot")
    while True:
        if input() == 'N':
            bot.stop_polling()
            print("Bot has been stopped")
            break

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, 'Hello!')
    
@bot.message_handler(commands=["give"])

def send_variable_image(message):
    path = "E:/JPG"
    photo_list = glob.glob(os.path.join(path, '*.jpg'))
    chat_id = message.chat.id
    photo = random.choice(photo_list)
    with open(photo, 'rb') as photo:
        bot.send_photo(chat_id, photo)




polling_thread = threading.Thread(target=bot.polling, args=(True, 5))
polling_thread.daemon = True
polling_thread.start()

# Start the stop_bot thread
stop_bot_thread = threading.Thread(target=stop_bot)
stop_bot_thread.start()
