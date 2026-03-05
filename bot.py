import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище (пока не подключили библиотеку supabase, используем память для теста кнопок)
user_data = {}

STRINGS = {
    "ua": {
        "welcome": "🇺🇦 Вітаю у головному меню!",
        "settings_menu": "⚙️ Що саме хочете налаштувати?",
        "weather_check": "Напишіть назву міста для прогнозу:",
        "support_contact": "Зв'язок з адміном: @YourUsername",
        "btn_weather": "🌤 Перевірити погоду",
        "btn_settings": "⚙️ Мої Налаштування",
        "btn_help": "🆘 Підтримка"
    },
    "en": {
        "welcome": "🇬🇧 Welcome to the main menu!",
        "settings_menu": "⚙️ What do you want to configure?",
        "weather_check": "Type the city name for the forecast:",
        "support_contact": "Contact admin: @YourUsername",
        "btn_weather": "🌤 Check Weather",
        "btn_settings": "⚙️ My Settings",
        "btn_help": "🆘 Support"
    }
}

# --- СЕРВЕР ---
async def handle(request): return web.Response(text="OK")
async def start_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()

# --- КНОПКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_data[message.from_user.id] = {"lang": "ua"} # По умолчанию
    builder = ReplyKeyboardBuilder()
    builder.button(text="🇺🇦 Українська"), builder.button(text="🇬🇧 English")
    await message.answer("Оберіть мову / Choose language:", reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_lang(message: types.Message):
    lang = "ua" if "🇺🇦" in message.text else "en"
    user_data[message.from_user.id]["lang"] = lang
    await show_main_menu(message)

async def show_main_menu(message: types.Message):
    lang = user_data[message.from_user.id]["lang"]
    t = STRINGS[lang]
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text=t["btn_weather"]))
    builder.row(types.KeyboardButton(text=t["btn_settings"]), types.KeyboardButton(text=t["btn_help"]))
    await message.answer(t["welcome"], reply_markup=builder.as_markup(resize_keyboard=True))

# ОБРАБОТКА КНОПОК МЕНЮ
@dp.message(F.text.in_(["🌤 Перевірити погоду", "🌤 Check Weather"]))
async def weather_click(message: types.Message):
    lang = user_data.get(message.from_user.id, {"lang":"en"})["lang"]
    await message.answer(STRINGS[lang]["weather_check"])

@dp.message(F.text.in_(["⚙️ Мої Налаштування", "⚙️ My Settings"]))
async def settings_click(message: types.Message):
    lang = user_data.get(message.from_user.id, {"lang":"en"})["lang"]
    await message.answer(STRINGS[lang]["settings_menu"])

@dp.message(F.text.in_(["🆘 Підтримка", "🆘 Support"]))
async def help_click(message: types.Message):
    lang = user_data.get(message.from_user.id, {"lang":"en"})["lang"]
    await message.answer(STRINGS[lang]["support_contact"])

async def main():
    await start_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
