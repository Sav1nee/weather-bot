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

# Логирование для Render
logging.basicConfig(level=logging.INFO)

# Инициализация API
TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Состояния для ввода данных (FSM)
class Setup(StatesGroup):
    waiting_for_city = State()
    waiting_for_bike_limit = State()
    waiting_for_walk_limit = State()

# --- Вспомогательные функции ---
async def get_user(user_id):
    """Получает данные пользователя из Supabase или создает нового"""
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        logging.info(f"New user {user_id} detected. Creating profile...")
        data = {"id": user_id, "language": "ua", "city": "Kyiv", "bike_wind_limit": 7.0, "walk_wind_limit": 5.0}
        supabase.table("profiles").insert(data).execute()
        return data
    return res.data[0]

# --- Клавиатуры ---
def get_main_kb(lang):
    builder = ReplyKeyboardBuilder()
    if lang == "ua":
        builder.row(types.KeyboardButton(text="🌤 Перевірити погоду"))
        builder.row(types.KeyboardButton(text="⚙️ Налаштування"), types.KeyboardButton(text="🆘 Підтримка"))
    else:
        builder.row(types.KeyboardButton(text="🌤 Check Weather"))
        builder.row(types.KeyboardButton(text="⚙️ Settings"), types.KeyboardButton(text="🆘 Support"))
    return builder.as_markup(resize_keyboard=True)

# --- Обработчики команд ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🇺🇦 Українська"), builder.button(text="🇬🇧 English")
    await message.answer("Оберіть мову / Choose language:", reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English"]))
async def set_language(message: types.Message):
    lang = "ua" if "🇺🇦" in message.text else "en"
    supabase.table("profiles").upsert({"id": message.from_user.id, "language": lang}).execute()
    welcome_text = "Вітаю у головному меню!" if lang == "ua" else "Welcome to main menu!"
    await message.answer(welcome_text, reply_markup=get_main_kb(lang))

# --- Секция Настроек ---
@dp.message(F.text.in_(["⚙️ Налаштування", "⚙️ Settings"]))
async def settings_menu(message: types.Message):
    user = await get_user(message.from_user.id)
    lang = user['language']
    
    text = (
        f"<b>{ 'Твої налаштування' if lang == 'ua' else 'Your Settings' }:</b>\n\n"
        f"🏙 { 'Місто' if lang == 'ua' else 'City' }: <code>{user['city']}</code>\n"
        f"🚲 { 'Вело-вітер' if lang == 'ua' else 'Bike wind' }: <code>{user['bike_wind_limit']} м/с</code>\n"
        f"🥾 { 'Хайкінг-вітер' if lang == 'ua' else 'Hike wind' }: <code>{user['walk_wind_limit']} м/с</code>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🏙 City", callback_data="set_city")
    kb.button(text="🚲 Bike Limit", callback_data="set_bike")
    kb.button(text="🥾 Hike Limit", callback_data="set_hike")
    kb.button(text="⬅️ Back", callback_data="back_to_main")
    kb.adjust(2)
    
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# --- Обработка ввода (FSM) ---
@dp.callback_query(F.data == "set_city")
async def start_set_city(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_city)
    await call.message.answer("Введіть назву вашого міста:")
    await call.answer()

@dp.message(Setup.waiting_for_city)
async def process_city(message: types.Message, state: FSMContext):
    supabase.table("profiles").update({"city": message.text}).eq("id", message.from_user.id).execute()
    await state.clear()
    user = await get_user(message.from_user.id)
    await message.answer(f"✅ Місто змінено на: {message.text}", reply_markup=get_main_kb(user['language']))

@dp.callback_query(F.data == "set_bike")
async def start_set_bike(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Setup.waiting_for_bike_limit)
    await call.message.answer("Введіть ліміт вітру для вело (тільки число, наприклад 8):")
    await call.answer()

@dp.message(Setup.waiting_for_bike_limit)
async def process_bike(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        supabase.table("profiles").update({"bike_wind_limit": val}).eq("id", message.from_user.id).execute()
        await state.clear()
        user = await get_user(message.from_user.id)
        await message.answer(f"✅ Вело-ліміт встановлено: {val} м/с", reply_markup=get_main_kb(user['language']))
    except:
        await message.answer("Будь ласка, введіть число (наприклад 7.5)")

# --- Погода (Заглушка) ---
@dp.message(F.text.in_(["🌤 Перевірити погоду", "🌤 Check Weather"]))
async def check_weather(message: types.Message):
    user = await get_user(message.from_user.id)
    city = user['city']
    await message.answer(f"🔍 Отримую прогноз для міста {city}...\n(Тут скоро буде реальна погода!)")

# --- Кнопка Назад и Поддержка ---
@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    await call.message.answer("📍 Головне меню", reply_markup=get_main_kb(user['language']))
    await call.answer()

@dp.message(F.text.in_(["🆘 Підтримка", "🆘 Support"]))
async def support(message: types.Message):
    await message.answer("Зв'язок з розробником: @Sav1neua")

# --- Запуск сервера ---
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
