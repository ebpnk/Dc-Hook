import json
from telebot import types
import logging
import requests
from io import BytesIO
from datetime import datetime, timedelta
import threading

# Загрузка конфигурации из файла
with open('cfg/configdc.json', 'r') as config_file:
    config = json.load(config_file)

DISCORD_WEBHOOK_URL = config['DISCORD_WEBHOOK_URL']
ALLOWED_USERS = config['ALLOWED_USERS']

logging.basicConfig(level=logging.INFO)

# Словарь для управления состоянием каждого пользователя
user_sessions = {}

def setup(bot, chat_id):
    @bot.message_handler(func=lambda message: message.text == "Отправка в Discord")
    def start_discord_session(message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if user_id not in ALLOWED_USERS:
            bot.send_message(chat_id, "У вас нет доступа к этой команде.")
            logging.info(f"Попытка доступа пользователя {user_id} была отклонена.")
            return

        if chat_id not in user_sessions:
            user_sessions[chat_id] = {}
            logging.info(f"Начало сессии для пользователя {chat_id}")
            prompt_user(message, bot)
        else:
            bot.send_message(chat_id, "Вы уже находитесь в сессии отправки в Discord. Введите сообщение или отправьте картинку.")

def prompt_user(message, bot):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    back_button = types.KeyboardButton("Назад")
    markup.add(back_button)
    msg = bot.send_message(chat_id, "Введите сообщение или отправьте картинку для отправки в Discord:", reply_markup=markup)
    bot.register_next_step_handler(msg, handle_user_input, bot)

def handle_user_input(message, bot):
    chat_id = message.chat.id
    if message.text == "Назад":
        del user_sessions[chat_id]
        bot.send_message(chat_id, "Вы вернулись в главное меню.")
        logging.info(f"Сессия для пользователя {chat_id} завершена (назад)")
        return

    if message.content_type == 'text':
        user_sessions[chat_id]['content'] = message.text
        ask_for_date(message, bot)
    elif message.content_type == 'photo':
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        file_data = bot.download_file(file_info.file_path)
        image = BytesIO(file_data)
        user_sessions[chat_id]['file'] = image
        if message.caption:
            user_sessions[chat_id]['content'] = message.caption
        ask_for_date(message, bot)
    else:
        bot.send_message(chat_id, "Пожалуйста, отправьте текстовое сообщение или картинку.")
        bot.register_next_step_handler(message, handle_user_input, bot)

def ask_for_date(message, bot):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "Введите дату в формате ДД.ММ.ГГГГ:")
    bot.register_next_step_handler(msg, handle_date_input, bot)

def handle_date_input(message, bot):
    chat_id = message.chat.id
    try:
        date = datetime.strptime(message.text, '%d.%m.%Y')
        user_sessions[chat_id]['date'] = date
        ask_for_time(message, bot)
    except ValueError:
        bot.send_message(chat_id, "Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.")
        ask_for_date(message, bot)

def ask_for_time(message, bot):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "Введите время в формате ЧЧ:ММ:")
    bot.register_next_step_handler(msg, handle_time_input, bot)

def handle_time_input(message, bot):
    chat_id = message.chat.id
    try:
        time = datetime.strptime(message.text, '%H:%M').time()
        send_time = datetime.combine(user_sessions[chat_id]['date'], time)
        if send_time < datetime.now():
            raise ValueError("Дата и время не могут быть в прошлом.")
        user_sessions[chat_id]['send_time'] = send_time
        content = user_sessions[chat_id].get('content', None)
        file = user_sessions[chat_id].get('file', None)
        schedule_task(send_time, content, file)
        bot.send_message(chat_id, "Сообщение запланировано для отправки в Discord!")
    except ValueError as e:
        bot.send_message(chat_id, f"Ошибка: {e}. Пожалуйста, введите время в формате ЧЧ:ММ.")
        ask_for_time(message, bot)
        return
    
    # Закрываем сессию и возвращаемся к меню
    del user_sessions[chat_id]
    bot.send_message(chat_id, "Вы вернулись в главное меню.")
    logging.info(f"Сессия для пользователя {chat_id} завершена")

def schedule_task(send_time, content, file):
    def task():
        send_to_discord(content, file)

    delay = (send_time - datetime.now()).total_seconds()
    if delay > 0:
        threading.Timer(delay, task).start()
        logging.info(f"Сообщение запланировано на {send_time}")
    else:
        logging.error("Заданное время уже прошло")

def send_to_discord(content=None, file=None):
    data = {
        'content': '@everyone\n' + content if content else '@everyone'
    }
    files = {}

    if file:
        files['file'] = ('image.jpg', file)

    response = requests.post(DISCORD_WEBHOOK_URL, data=data, files=files)
    response.raise_for_status()  # Выбрасывает исключение в случае ошибки

def menu_info():
    return {
        "title": "Отправка в Discord",
        "command": "Отправка в Discord"
    }

def register_handlers(bot):
    pass  # Обработчики обратных вызовов больше не нужны
