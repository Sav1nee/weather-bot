import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from supabase import create_client
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# Инициализация
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Состояния для ввода данных
class Setup(StatesGroup):
    waiting_for_city = State()
    waiting_for_bike_wind = State()

# --- Логика БД ---
async def get_user(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        data = {"id": user_id, "city": "Kyiv", "language": "ua"}
        supabase.table("profiles").insert(data).execute()
        return data
    return res.data[0]

# --- Главное меню ---
async def main_menu(message: types.Message, user_id: int):
    user = await get_user(user_id)
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🌤 Погода"))
    builder.row(types.KeyboardButton(text="⚙️ Налаштування"))
    await message.answer("📍 Головне меню", reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await main_menu(message, message.from_user.id)

# --- Настройки ---
@dp.message(F.text == "⚙️ Налаштування")
async def settings(message: types.Message):
    user = await get_user(message.from_user.id)
    text = (f"📝 Твої налаштування:\n"
            f"🏙 Місто: {user.get('city')}\n"
            f"🚲 Вело-вітер: до {user.get('bike_wind_limit', 7)} м/с\n\n"
            f"Обери, що змінити:")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙 Змінити місто", callback_data="edit_city")
    builder.button(text="🚲 Ліміт вітру (Вело)", callback_data="edit_bike")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup())

# --- Процесс изменения города ---
@dp.callback_query(F.data == "edit_city")
async def edit_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_city)
    await call.message.answer("Напишіть назву міста:")
    await call.answer()

@dp.message(Setup.waiting_for_city)
async def save_city(message: types.Message, state: FSMContext):
    city_name = message.text
    supabase.table("profiles").update({"city": city_name}).eq("id", message.from_user.id).execute()
    await state.clear()
    await message.answer(f"✅ Місто {city_name} збережено!")
    await main_menu(message, message.from_user.id)

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
