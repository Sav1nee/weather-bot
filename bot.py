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

logging.basicConfig(level=logging.INFO)

# Инициализация
TOKEN = os.getenv("BOT_TOKEN")
S_URL = os.getenv("SUPABASE_URL")
S_KEY = os.getenv("SUPABASE_KEY")
W_API_KEY = os.getenv("WEATHER_API_KEY")

supabase = create_client(S_URL, S_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class Setup(StatesGroup):
    waiting_for_city = State()
    waiting_for_bike = State()
    waiting_for_hike = State()

async def get_user(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        data = {"id": user_id, "language": "ua", "city": "Kyiv", "bike_wind_limit": 7.0, "walk_wind_limit": 5.0}
        supabase.table("profiles").insert(data).execute()
        return data
    return res.data[0]

async def get_weather(city):
    # Запрос к OpenWeather
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={W_API_KEY}&units=metric&lang=ua"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logging.error(f"Weather error: {e}")
            return None

def main_kb(lang):
    kb = ReplyKeyboardBuilder()
    btn_weather = "🌤 Перевірити погоду" if lang == "ua" else "🌤 Check Weather"
    btn_settings = "⚙️ Налаштування" if lang == "ua" else "⚙️ Settings"
    btn_support = "🆘 Підтримка" if lang == "ua" else "🆘 Support"
    kb.row(types.KeyboardButton(text=btn_weather))
    kb.row(types.KeyboardButton(text=btn_settings), types.KeyboardButton(text=btn_support))
    return kb.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    kb = ReplyKeyboardBuilder()
    kb.button(text="🇺🇦 Українська"), kb.button(text="🇬🇧 English")
    await message.answer("Оберіть мову / Choose language:", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_lang(message: types.Message):
    l = "ua" if "🇺🇦" in message.text else "en"
    supabase.table("profiles").upsert({"id": message.from_user.id, "language": l}).execute()
    await message.answer("✅ Готово!", reply_markup=main_kb(l))

# --- ЛОГИКА ПРОГНОЗА ---
@dp.message(F.text.in_(["🌤 Перевірити погоду", "🌤 Check Weather"]))
async def weather_check(message: types.Message):
    user = await get_user(message.from_user.id)
    msg_wait = await message.answer("🔍 Зачекайте, отримую дані...")
    
    data = await get_weather(user['city'])
    await msg_wait.delete()

    if not data:
        await message.answer("❌ Місто не знайдено. Змініть його в налаштуваннях (латиницею, напр. Stockholm).")
        return

    # Извлекаем данные
    temp = round(data['main']['temp'])
    feels_like = round(data['main']['feels_like'])
    humidity = data['main']['humidity']
    wind = data['wind']['speed']
    desc = data['weather'][0]['description'].capitalize()
    city = data['name']
    
    # Сравниваем с лимитами
    bike_ok = "✅ Можна" if wind <= user['bike_wind_limit'] else "🛑 Сильний вітер"
    hike_ok = "✅ Можна" if wind <= user['walk_wind_limit'] else "🛑 Сильний вітер"

    res = (
        f"<b>📍 {city} — {desc}</b>\n\n"
        f"🌡 Температура: <b>{temp}°C</b> (відчувається як {feels_like}°C)\n"
        f"💧 Вологість: <b>{humidity}%</b>\n"
        f"💨 Вітер: <b>{wind} м/с</b>\n\n"
        f"🚲 <b>Для вело:</b> {bike_ok}\n"
        f"🥾 <b>Для прогулянки:</b> {hike_ok}"
    )
    await message.answer(res, parse_mode="HTML")

# --- НАСТРОЙКИ ---
@dp.message(F.text.in_(["⚙️ Налаштування", "⚙️ Settings"]))
async def settings(message: types.Message):
    u = await get_user(message.from_user.id)
    txt = (
        f"⚙️ <b>Твої параметри:</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🏙 Місто: <code>{u['city']}</code>\n"
        f"🚲 Вело-ліміт вітру: <b>{u['bike_wind_limit']} м/с</b>\n"
        f"🥾 Хайкінг-ліміт вітру: <b>{u['walk_wind_limit']} м/с</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Оберіть параметр для зміни:"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🏙 Змінити місто", callback_data="st_city")
    kb.button(text="🚲 Ліміт для вело", callback_data="st_bike")
    kb.button(text="🥾 Ліміт для хайкінгу", callback_data="st_hike")
    kb.adjust(1)
    await message.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "st_city")
async def st_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_city)
    await call.message.answer("⌨️ Напишіть назву міста (наприклад: Kyiv):")
    await call.answer()

@dp.message(Setup.waiting_for_city)
async def save_city(message: types.Message, state: FSMContext):
    city = message.text
    supabase.table("profiles").update({"city": city}).eq("id", message.from_user.id).execute()
    await state.clear()
    await message.answer(f"✅ Місто змінено на: <b>{city}</b>", parse_mode="HTML")

@dp.callback_query(F.data == "st_bike")
async def st_bike(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_bike)
    await call.message.answer("🚲 Введіть макс. швидкість вітру для вело (м/с):")
    await call.answer()

@dp.message(Setup.waiting_for_bike)
async def save_bike(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        supabase.table("profiles").update({"bike_wind_limit": val}).eq("id", message.from_user.id).execute()
        await state.clear()
        await message.answer(f"✅ Новий ліміт для вело: {val} м/с")
    except:
        await message.answer("❌ Будь ласка, введіть число.")

@dp.message(F.text.in_(["🆘 Підтримка", "🆘 Support"]))
async def support(message: types.Message):
    await message.answer("🆘 Зв'язок з розробником: @savinee\n\nБот допоможе визначити, чи комфортно сьогодні займатися спортом на вулиці.")

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
