import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from supabase import create_client
from aiohttp import web

# Включаем логирование, чтобы видеть ошибки в Render
logging.basicConfig(level=logging.INFO)

# Инициализация ключей
TOKEN = os.getenv("BOT_TOKEN")
S_URL = os.getenv("SUPABASE_URL")
S_KEY = os.getenv("SUPABASE_KEY")

try:
    supabase = create_client(S_URL, S_KEY)
    logging.info("Supabase client created successfully")
except Exception as e:
    logging.error(f"Failed to connect to Supabase: {e}")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Тексты (добавил кнопку Назад) ---
STRINGS = {
    "ua": {
        "start": "Оберіть мову:",
        "main_menu": "📍 Головне меню",
        "settings_info": "📝 Твої налаштування:\n🏙 Місто: {city}\n🚲 Вело: до {b_w}м/с\n🥾 Хайкінг: до {w_w}м/с\n\nЩо саме змінити?",
        "btn_weather": "🌤 Погода",
        "btn_settings": "⚙️ Налаштування",
        "btn_back": "⬅️ Назад",
        "set_city": "Напишіть назву міста (наприклад: Stockholm):"
    }
}

# --- Функция получения пользователя с защитой ---
async def get_user_data(user_id):
    try:
        res = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if not res.data:
            logging.info(f"Creating new user {user_id}")
            new_user = {"id": user_id, "language": "ua", "city": "Kyiv"}
            supabase.table("profiles").insert(new_user).execute()
            return {"id": user_id, "language": "ua", "city": "Kyiv", "bike_wind_limit": 7.0, "walk_wind_limit": 5.0}
        return res.data[0]
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return None

# --- Обработка кнопок ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🇺🇦 Українська"), builder.button(text="🇬🇧 English")
    await message.answer("🇺🇦 Оберіть мову / 🇬🇧 Choose language:", reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_language(message: types.Message):
    lang = "ua" if "🇺🇦" in message.text else "en"
    user_id = message.from_user.id
    try:
        supabase.table("profiles").upsert({"id": user_id, "language": lang}).execute()
        await show_main_menu(message)
    except Exception as e:
        await message.answer(f"Помилка бази даних: {e}")

async def show_main_menu(message: types.Message):
    user = await get_user_data(message.from_user.id)
    lang = user['language'] if user else "ua"
    
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🌤 Погода"))
    builder.row(types.KeyboardButton(text="⚙️ Налаштування"))
    await message.answer("📍 Головне меню", reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text == "⚙️ Налаштування")
async def settings_panel(message: types.Message):
    user = await get_user_data(message.from_user.id)
    if not user:
        await message.answer("Не вдалося завантажити профіль.")
        return

    text = STRINGS["ua"]["settings_info"].format(
        city=user.get('city', 'Kyiv'), 
        b_w=user.get('bike_wind_limit', 7.0), 
        w_w=user.get('walk_wind_limit', 5.0)
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙 Змінити місто", callback_data="set_city")
    builder.button(text="🚲 Вело: Вітер", callback_data="set_bike")
    builder.button(text="⬅️ Назад", callback_data="to_main")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Пример обработки Inline кнопок
@dp.callback_query(F.data == "to_main")
async def back_to_main(call: types.CallbackQuery):
    await show_main_menu(call.message)
    await call.answer()

# --- Сервер ---
async def handle(request): return web.Response(text="OK")
async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    logging.info("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
