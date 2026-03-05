import asyncio
import os
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from supabase import create_client
from aiohttp import web

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Конфигурация из Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
S_URL = os.getenv("SUPABASE_URL")
S_KEY = os.getenv("SUPABASE_KEY")
W_API_KEY = os.getenv("WEATHER_API_KEY")

# Инициализация клиентов
supabase = create_client(S_URL, S_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class Setup(StatesGroup):
    waiting_for_city = State()
    waiting_for_bike = State()
    waiting_for_hike = State()

# --- Логика Базы Данных ---
async def get_user(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        data = {"id": user_id, "language": "ua", "city": "Kyiv", "bike_wind_limit": 7.0, "walk_wind_limit": 5.0}
        supabase.table("profiles").insert(data).execute()
        return data
    return res.data[0]

# --- Логика Погоды ---
async def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={W_API_KEY}&units=metric"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

# --- Клавиатуры ---
def main_kb(lang):
    kb = ReplyKeyboardBuilder()
    if lang == "ua":
        kb.row(types.KeyboardButton(text="🌤 Перевірити погоду"))
        kb.row(types.KeyboardButton(text="⚙️ Налаштування"), types.KeyboardButton(text="🆘 Підтримка"))
    else:
        kb.row(types.KeyboardButton(text="🌤 Check Weather"))
        kb.row(types.KeyboardButton(text="⚙️ Settings"), types.KeyboardButton(text="🆘 Support"))
    return kb.as_markup(resize_keyboard=True)

# --- Обработчики ---

@dp.message(Command("start"))
async def start(message: types.Message):
    kb = ReplyKeyboardBuilder()
    kb.button(text="🇺🇦 Українська"), kb.button(text="🇬🇧 English")
    await message.answer("Оберіть мову / Choose language:", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_lang(message: types.Message):
    l = "ua" if "🇺🇦" in message.text else "en"
    supabase.table("profiles").upsert({"id": message.from_user.id, "language": l}).execute()
    txt = "Головне меню" if l == "ua" else "Main Menu"
    await message.answer(f"✅ {txt}", reply_markup=main_kb(l))

@dp.message(F.text.in_(["🌤 Перевірити погоду", "🌤 Check Weather"]))
async def weather_check(message: types.Message):
    user = await get_user(message.from_user.id)
    data = await get_weather(user['city'])
    
    if not data:
        await message.answer("❌ Не вдалося знайти місто. Перевірте назву в налаштуваннях.")
        return

    temp = data['main']['temp']
    wind = data['wind']['speed']
    city = data['name']
    
    # Логика сравнения
    bike_status = "🟢 OK" if wind <= user['bike_wind_limit'] else "🛑 TOO WINDY"
    hike_status = "🟢 OK" if wind <= user['walk_wind_limit'] else "🛑 TOO WINDY"
    
    res = (
        f"<b>📍 {city}</b>\n"
        f"🌡 Температура: {temp}°C\n"
        f"💨 Вітер: {wind} м/с\n\n"
        f"🚲 <b>Cycling:</b> {bike_status} (limit: {user['bike_wind_limit']})\n"
        f"🥾 <b>Hiking:</b> {hike_status} (limit: {user['walk_wind_limit']})"
    )
    await message.answer(res, parse_mode="HTML")

@dp.message(F.text.in_(["⚙️ Налаштування", "⚙️ Settings"]))
async def settings(message: types.Message):
    u = await get_user(message.from_user.id)
    txt = f"⚙️ <b>Налаштування:</b>\n\n🏙 Місто: {u['city']}\n🚲 Вело-ліміт: {u['bike_wind_limit']} м/с\n🥾 Хайкінг-ліміт: {u['walk_wind_limit']} м/с"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🏙 City", callback_data="st_city")
    kb.button(text="🚲 Bike", callback_data="st_bike")
    kb.button(text="🥾 Hike", callback_data="st_hike")
    kb.adjust(1)
    await message.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")

# --- FSM Обработка ввода ---
@dp.callback_query(F.data == "st_city")
async def st_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_city)
    await call.message.answer("Введіть назву міста:")
    await call.answer()

@dp.message(Setup.waiting_for_city)
async def save_city(message: types.Message, state: FSMContext):
    supabase.table("profiles").update({"city": message.text}).eq("id", message.from_user.id).execute()
    await state.clear()
    await message.answer(f"✅ Місто змінено на {message.text}")

@dp.callback_query(F.data == "st_bike")
async def st_bike(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_bike)
    await call.message.answer("Введіть ліміт вітру для вело (м/с):")
    await call.answer()

@dp.message(Setup.waiting_for_bike)
async def save_bike(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        supabase.table("profiles").update({"bike_wind_limit": val}).eq("id", message.from_user.id).execute()
        await state.clear()
        await message.answer(f"✅ Ліміт вело оновлено: {val} м/с")
    except:
        await message.answer("❌ Введіть число!")

@dp.message(F.text.in_(["🆘 Підтримка", "🆘 Support"]))
async def support(message: types.Message):
    await message.answer("🆘 Зв'язок з розробником: @savinee\nЗнайшли помилку? Пишіть нам!")

# --- Запуск ---
async def handle(request): return web.Response(text="OK")
async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
