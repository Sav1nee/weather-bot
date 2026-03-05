import asyncio
import os
import logging
import aiohttp
from datetime import datetime
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

# --- Утилиты для ветра ---
def get_wind_direction(deg):
    directions = ['⬆️ Пн', '↗️ Пн-Сх', '➡️ Сх', '↘️ Пд-Сх', '⬇️ Пд', '↙️ Пд-Зх', '⬅️ Зх', '↖️ Пн-Зх']
    index = int((deg + 22.5) / 45) % 8
    return directions[index]

# --- Клавиатуры ---
def main_menu_kb(lang):
    kb = ReplyKeyboardBuilder()
    text = "🌤 Прогноз на 3 дні" if lang == "ua" else "🌤 3-Day Forecast"
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
    await message.answer("✅ Налаштовано!", reply_markup=main_menu_kb(lang))

# --- ЛОГИКА ПРОГНОЗА НА 3 ДНЯ ---
@dp.message(F.text.in_(["🌤 Прогноз на 3 дні", "🌤 3-Day Forecast"]))
async def show_forecast(message: types.Message):
    user = await get_user(message.from_user.id)
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={user['city']}&appid={W_API_KEY}&units=metric&lang=ua"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                await message.answer("❌ Місто не знайдено. Перевірте назву в налаштуваннях.")
                return
            data = await resp.json()

    # Группируем данные: 3 дня, 3 временные точки (9:00, 15:00, 21:00)
    forecast_text = f"<b>📅 Прогноз для {data['city']['name']}</b>\n"
    current_date = ""
    count_days = 0
    
    # OpenWeather дает прогноз каждые 3 часа. Фильтруем нужные нам часы.
    target_hours = ["09:00:00", "15:00:00", "21:00:00"]
    
    for item in data['list']:
        dt_obj = datetime.strptime(item['dt_txt'], '%Y-%m-%d %H:%M:%S')
        date_str = dt_obj.strftime('%d.%m')
        time_str = dt_obj.strftime('%H:%M')
        
        if date_str != current_date:
            if count_days >= 3: break
            forecast_text += f"\n🔹 <b>{date_str}</b>\n"
            current_date = date_str
            count_days += 1
            
        if item['dt_txt'].split()[1] in target_hours:
            temp = round(item['main']['temp'])
            wind = item['wind']['speed']
            direction = get_wind_direction(item['wind']['deg'])
            
            # Вердикт по ветру
            status = "✅" if wind <= user['bike_wind_limit'] else "🛑"
            
            forecast_text += f"  {time_str} | {temp}°C | {wind}м/с {direction} {status}\n"

    forecast_text += f"\n<i>{status} — перевірка по ліміту вело ({user['bike_wind_limit']} м/с)</i>"
    await message.answer(forecast_text, parse_mode="HTML")

# --- НАСТРОЙКИ (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ) ---
@dp.message(F.text.in_(["⚙️ Налаштування", "⚙️ Settings"]))
async def settings(message: types.Message):
    u = await get_user(message.from_user.id)
    text = (f"⚙️ <b>Параметри:</b>\n🏙 Місто: <code>{u['city']}</code>\n"
            f"🚲 Вело: <b>{u['bike_wind_limit']} м/с</b>\n🥾 Хайкінг: <b>{u['walk_wind_limit']} м/с</b>")
    kb = InlineKeyboardBuilder()
    kb.button(text="🏙 Місто", callback_data="set_city")
    kb.button(text="🚲 Вело", callback_data="set_bike")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "set_city")
async def edit_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.city); await call.message.answer("⌨️ Назва міста (English):"); await call.answer()

@dp.message(Setup.city)
async def save_city(message: types.Message, state: FSMContext):
    supabase.table("profiles").update({"city": message.text}).eq("id", message.from_user.id).execute()
    await state.clear(); await message.answer(f"✅ Місто: {message.text}")

@dp.callback_query(F.data == "set_bike")
async def edit_bike(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.bike); await call.message.answer("🚲 Ліміт вітру (м/с):"); await call.answer()

@dp.message(Setup.bike)
async def save_bike(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        supabase.table("profiles").update({"bike_wind_limit": val}).eq("id", message.from_user.id).execute()
        await state.clear(); await message.answer(f"✅ Ліміт: {val} м/с")
    except: await message.answer("❌ Число!")

# --- ЗАПУСК ---
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
