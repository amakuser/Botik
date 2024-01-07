from telebot import TeleBot

TOKEN = '6957693939:AAHO1RvZU8IUnRjL7CvUclI7j7mMSk7CESA'
bot = TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, 'Hello!')

bot.polling(none_stop=True, interval=5)