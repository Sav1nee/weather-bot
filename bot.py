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

# --- Вспомогательные функции ---
async def get_user(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        data = {"id": user_id, "language": "ua", "city": "Kyiv", "bike_wind_limit": 7.0, "forecast_days": 3}
        supabase.table("profiles").insert(data).execute()
        return data
    return res.data[0]

def get_wind_dir(deg):
    # Превращаем градусы в понятные стрелочки
    dirs = ['⬆️ Пн', '↗️ Пн-Сх', '➡️ Сх', '↘️ Пд-Сх', '⬇️ Пд', '↙️ Пд-Зх', '⬅️ Зх', '↖️ Пн-Зх']
    return dirs[int((deg + 22.5) / 45) % 8]

def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="🌤 Отримати прогноз"))
    kb.row(types.KeyboardButton(text="⚙️ Налаштування"), types.KeyboardButton(text="🆘 Support"))
    return kb.as_markup(resize_keyboard=True)

# --- Обработчики ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🌤 Вітаю! Я допоможу спланувати твій день.", reply_markup=main_kb())

# --- ГЛАВНАЯ ЛОГИКА ПРОГНОЗА ---
@dp.message(F.text == "🌤 Отримати прогноз")
async def send_forecast(message: types.Message):
    user = await get_user(message.from_user.id)
    # Используем 5-day forecast API
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={user['city']}&appid={W_API_KEY}&units=metric&lang=ua"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return await message.answer("❌ Місто не знайдено. Змініть назву в налаштуваннях (напр. Stockholm).")
            data = await resp.json()

    days_limit = user.get('forecast_days', 3)
    target_times = ["09:00:00", "15:00:00", "21:00:00"]
    
    # Группируем данные по дням
    forecast_by_days = {}
    for item in data['list']:
        dt = datetime.strptime(item['dt_txt'], '%Y-%m-%d %H:%M:%S')
        date_str = dt.strftime('%d.%m (%A)')
        time_part = item['dt_txt'].split()[1]
        
        if time_part in target_times:
            if date_str not in forecast_by_days:
                if len(forecast_by_days) >= days_limit: break
                forecast_by_days[date_str] = []
            forecast_by_days[date_str].append(item)

    # Отправляем сообщение для каждого дня
    for day, readings in forecast_by_days.items():
        text = f"<b>📅 {day}</b>\n"
        text += "━━━━━━━━━━━━━━\n"
        
        for r in readings:
            t_label = r['dt_txt'].split()[1][:5]
            temp = round(r['main']['temp'])
            wind = r['wind']['speed']
            hum = r['main']['humidity']
            wdir = get_wind_dir(r['wind']['deg'])
            desc = r['weather'][0]['description']
            
            # Сравниваем с твоим лимитом для вело
            status = "✅" if wind <= user['bike_wind_limit'] else "🛑"
            
            text += f"🕒 <b>{t_label}</b> | {temp}°C | {wind}м/с {wdir} {status}\n"
            text += f"<i>{desc.capitalize()}, вологість {hum}%</i>\n"
            text += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        
        await message.answer(text, parse_mode="HTML")

# --- НАСТРОЙКИ ---
@dp.message(F.text == "⚙️ Налаштування")
async def settings(message: types.Message):
    u = await get_user(message.from_user.id)
    text = (f"⚙️ <b>Твої налаштування:</b>\n"
            f"🏙 Місто: <code>{u['city']}</code>\n"
            f"🚲 Вело-ліміт: <b>{u['bike_wind_limit']} м/с</b>\n"
            f"📅 Прогноз на: <b>{u.get('forecast_days', 3)} дні(в)</b>")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🏙 Змінити місто", callback_data="set_city")
    kb.button(text="🚲 Вело-ліміт", callback_data="set_bike")
    kb.button(text="📅 К-сть днів", callback_data="set_days_menu")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# Выбор количества дней
@dp.callback_query(F.data == "set_days_menu")
async def days_menu(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    for d in [1, 3, 5]: # OpenWeather Free ограничен 5 днями
        kb.button(text=f"{d} дн.", callback_data=f"save_days_{d}")
    kb.adjust(3)
    await call.message.edit_text("На скільки днів показувати прогноз?", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("save_days_"))
async def save_days(call: types.CallbackQuery):
    days = int(call.data.split("_")[-1])
    supabase.table("profiles").update({"forecast_days": days}).eq("id", call.from_user.id).execute()
    await call.message.answer(f"✅ Тепер буду показувати прогноз на {days} дні(в).")
    await call.answer()

# --- Ввод города и лимита ---
@dp.callback_query(F.data == "set_city")
async def st_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.city); await call.message.answer("Напишіть місто (English):"); await call.answer()

@dp.message(Setup.city)
async def sv_city(message: types.Message, state: FSMContext):
    supabase.table("profiles").update({"city": message.text}).eq("id", message.from_user.id).execute()
    await state.clear(); await message.answer(f"✅ Місто: {message.text}")

@dp.callback_query(F.data == "set_bike")
async def st_bike(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.bike); await call.message.answer("Макс. вітер для вело (м/с):"); await call.answer()

@dp.message(Setup.bike)
async def sv_bike(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        supabase.table("profiles").update({"bike_wind_limit": val}).eq("id", message.from_user.id).execute()
        await state.clear(); await message.answer(f"✅ Ліміт: {val} м/с")
    except: await message.answer("Потрібно число.")

# --- Сервер ---
async def handle(r): return web.Response(text="OK")
async def main():
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
