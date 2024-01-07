import threading
#import telebot
import time
import sys
import os
import glob
import random
from telebot import TeleBot
from telebot import types

TOKEN = '6957693939:AAHO1RvZU8IUnRjL7CvUclI7j7mMSk7CESA'
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