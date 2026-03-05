import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiohttp import web

# --- ИНИЦИАЛИЗАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словарь для хранения данных (пока в памяти, позже подключим Supabase)
users = {}

# Тексты
STRINGS = {
    "ua": {
        "welcome": "Вітаю! Я допоможу налаштувати твій ідеальний день.",
        "choose_lang": "Оберіть мову:",
        "main_menu": "Головне меню",
        "settings": "⚙️ Мої Налаштування",
        "check": "🌤 Перевірити погоду",
        "help": "🆘 Підтримка",
        "support_msg": "Напишіть ваше питання. Ми відповімо якнайшвидше."
    },
    "en": {
        "welcome": "Welcome! I will help you set up your perfect day.",
        "choose_lang": "Choose language:",
        "main_menu": "Main Menu",
        "settings": "⚙️ My Settings",
        "check": "🌤 Check Weather",
        "help": "🆘 Support",
        "support_msg": "Write your question. We will get back to you soon."
    }
}

# --- СЕРВЕР ДЛЯ ЖИЗНЕСПОСОБНОСТИ (Render) ---
async def handle(request):
    return web.Response(text="Service is Active")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- ЛОГИКА БОТА ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    # Создаем базовый профиль при регистрации
    users[message.from_user.id] = {
        "lang": "ua",
        "city": None,
        "temp_min": 15,
        "wind_max": 10
    }
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="🇺🇦 Українська")
    builder.button(text="🇬🇧 English")
    await message.answer("🇺🇦 Оберіть мову / 🇬🇧 Choose language:", 
                         reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def select_lang(message: types.Message):
    lang = "ua" if "🇺🇦" in message.text else "en"
    users[message.from_user.id]["lang"] = lang
    
    await main_menu(message)

async def main_menu(message: types.Message):
    lang = users[message.from_user.id]["lang"]
    t = STRINGS[lang]
    
    builder = ReplyKeyboardBuilder()
    builder.button(text=t["check"])
    builder.button(text=t["settings"])
    builder.button(text=t["help"])
    builder.adjust(2)
    
    await message.answer(t["welcome"], reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🆘 Support", "🆘 Підтримка"]))
async def support(message: types.Message):
    lang = users[message.from_user.id]["lang"]
    await message.answer(STRINGS[lang]["support_msg"])

# --- ЗАПУСК ---
async def main():
    await start_webserver()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
