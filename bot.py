import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from supabase import create_client
from aiohttp import web

# Инициализация
TOKEN = os.getenv("BOT_TOKEN")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Тексты
STRINGS = {
    "ua": {
        "start": "Оберіть мову:",
        "main_menu": "📍 Головне меню",
        "settings_info": "📝 Твої налаштування:\n🏙 Місто: {city}\n🚲 Вело: до {b_w}м/с\n🥾 Хайкінг: до {w_w}м/с\n\nЩо змінити?",
        "btn_weather": "🌤 Погода",
        "btn_settings": "⚙️ Налаштування",
        "btn_back": "⬅️ Назад",
        "set_city": "Напишіть назву міста:"
    },
    "en": {
        "start": "Choose language:",
        "main_menu": "📍 Main Menu",
        "settings_info": "📝 Your settings:\n🏙 City: {city}\n🚲 Bike: up to {b_w}m/s\n🥾 Hike: up to {w_w}m/s\n\nWhat to change?",
        "btn_weather": "🌤 Weather",
        "btn_settings": "⚙️ Settings",
        "btn_back": "⬅️ Back",
        "set_city": "Enter city name:"
    }
}

# --- Вспомогательная функция базы ---
async def get_user(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        # Создаем запись, если её нет
        supabase.table("profiles").insert({"id": user_id, "city": "Kyiv"}).execute()
        return {"id": user_id, "city": "Kyiv", "language": "ua", "bike_wind_limit": 7, "walk_wind_limit": 5}
    return res.data[0]

# --- Обработка команд ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🇺🇦 Українська"), builder.button(text="🇬🇧 English")
    await message.answer(STRINGS["ua"]["start"], reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_language(message: types.Message):
    lang = "ua" if "🇺🇦" in message.text else "en"
    supabase.table("profiles").upsert({"id": message.from_user.id, "language": lang}).execute()
    await show_main_menu(message)

async def show_main_menu(message: types.Message):
    user = await get_user(message.from_user.id)
    lang = user['language']
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text=STRINGS[lang]["btn_weather"]))
    builder.row(types.KeyboardButton(text=STRINGS[lang]["btn_settings"]))
    await message.answer(STRINGS[lang]["main_menu"], reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["⚙️ Налаштування", "⚙️ Settings"]))
async def settings_panel(message: types.Message):
    user = await get_user(message.from_user.id)
    lang = user['language']
    
    # Формируем текст с текущими настройками
    text = STRINGS[lang]["settings_info"].format(
        city=user['city'], 
        b_w=user['bike_wind_limit'], 
        w_w=user['walk_wind_limit']
    )
    
    # Инлайн кнопки (прямо в сообщении)
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙 City", callback_data="set_city")
    builder.button(text="🚲 Bike Wind", callback_data="set_bike_wind")
    builder.button(text="🥾 Hike Wind", callback_data="set_walk_wind")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Пример обработки кнопки "City"
@dp.callback_query(F.data == "set_city")
async def ask_city(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    await callback.message.answer(STRINGS[user['language']]["set_city"])
    await callback.answer()

# --- Сервер для Render ---
async def handle(request): return web.Response(text="Live")
async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
