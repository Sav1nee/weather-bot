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
W_API_KEY = os.getenv("WEATHER_API_KEY")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
bot = Bot(token=TOKEN)
dp = Dispatcher()

class Setup(StatesGroup):
    city = State()
    bike = State()
    hike = State()

async def get_user(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        data = {"id": user_id, "language": "ua", "city": "Kyiv", "bike_wind_limit": 7.0, "walk_wind_limit": 5.0}
        supabase.table("profiles").insert(data).execute()
        return data
    return res.data[0]

# --- Функция запроса погоды ---
async def fetch_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={W_API_KEY}&units=metric&lang=ua"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except:
            return None

# --- Клавиатуры ---
def main_menu_kb(lang):
    kb = ReplyKeyboardBuilder()
    text = "🌤 Погода" if lang == "ua" else "🌤 Weather"
    set_text = "⚙️ Налаштування" if lang == "ua" else "⚙️ Settings"
    kb.row(types.KeyboardButton(text=text))
    kb.row(types.KeyboardButton(text=set_text), types.KeyboardButton(text="🆘 Support"))
    return kb.as_markup(resize_keyboard=True)

# --- Обработчики ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardBuilder()
    kb.button(text="🇺🇦 Українська"), kb.button(text="🇬🇧 English")
    await message.answer("Оберіть мову / Choose language:", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_lang(message: types.Message):
    lang = "ua" if "🇺🇦" in message.text else "en"
    supabase.table("profiles").upsert({"id": message.from_user.id, "language": lang}).execute()
    await message.answer("✅ Виконую...", reply_markup=main_menu_kb(lang))

# --- ЛОГИКА ПОГОДЫ (ТВОЯ СХЕМА) ---
@dp.message(F.text.in_(["🌤 Погода", "🌤 Weather", "🌤 Перевірити погоду"]))
async def show_weather(message: types.Message):
    user = await get_user(message.from_user.id)
    data = await fetch_weather(user['city'])
    
    if not data:
        await message.answer("❌ Місто не знайдено. Спробуйте написати назву латиницею в налаштуваннях (напр. Gothenburg).")
        return

    w = data['weather'][0]['description'].capitalize()
    temp = round(data['main']['temp'])
    wind = data['wind']['speed']
    hum = data['main']['humidity']
    
    # Сравнение с лимитами
    bike_res = "✅ OK" if wind <= user['bike_wind_limit'] else "🛑 Сильний вітер"
    hike_res = "✅ OK" if wind <= user['walk_wind_limit'] else "🛑 Сильний вітер"

    report = (
        f"<b>📍 {data['name']} — {w}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌡 Температура: <b>{temp}°C</b>\n"
        f"💨 Вітер: <b>{wind} м/с</b>\n"
        f"💧 Вологість: <b>{hum}%</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🚲 <b>Вело:</b> {bike_res} (ліміт {user['bike_wind_limit']})\n"
        f"🥾 <b>Хайкінг:</b> {hike_res} (ліміт {user['walk_wind_limit']})\n"
    )
    await message.answer(report, parse_mode="HTML")

# --- НАСТРОЙКИ ---
@dp.message(F.text.in_(["⚙️ Налаштування", "⚙️ Settings"]))
async def settings(message: types.Message):
    u = await get_user(message.from_user.id)
    text = (
        f"⚙️ <b>Параметри:</b>\n"
        f"🏙 Місто: <code>{u['city']}</code>\n"
        f"🚲 Вело-ліміт: <b>{u['bike_wind_limit']} м/с</b>\n"
        f"🥾 Хайкінг-ліміт: <b>{u['walk_wind_limit']} м/с</b>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🏙 Місто", callback_data="set_city")
    kb.button(text="🚲 Вело", callback_data="set_bike")
    kb.button(text="🥾 Хайкінг", callback_data="set_hike")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "set_city")
async def edit_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.city)
    await call.message.answer("⌨️ Напишіть назву міста латиницею (напр. Stockholm):")
    await call.answer()

@dp.message(Setup.city)
async def save_city(message: types.Message, state: FSMContext):
    supabase.table("profiles").update({"city": message.text}).eq("id", message.from_user.id).execute()
    await state.clear()
    await message.answer(f"✅ Місто змінено на <b>{message.text}</b>", parse_mode="HTML")

# --- Лимиты ветра ---
@dp.callback_query(F.data == "set_bike")
async def edit_bike(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.bike)
    await call.message.answer("🚲 Введіть ліміт вітру (м/с):")
    await call.answer()

@dp.message(Setup.bike)
async def save_bike(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        supabase.table("profiles").update({"bike_wind_limit": val}).eq("id", message.from_user.id).execute()
        await state.clear()
        await message.answer(f"✅ Вело-ліміт: {val} м/с")
    except:
        await message.answer("❌ Введіть число!")

@dp.message(F.text == "🆘 Support")
async def support(message: types.Message):
    await message.answer("🆘 Зв'язок: @your_handle\nВідправте опис проблеми.")

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
