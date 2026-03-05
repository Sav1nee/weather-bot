import asyncio
import aiohttp
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

activities_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚴 Велосипед")],
        [KeyboardButton(text="🚶 Прогулянка")],
        [KeyboardButton(text="🥾 Хайкінг")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привіт! 🌤\n\nНапиши назву міста (наприклад: Gothenburg або Київ)",
    )

async def get_coordinates(city):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            if "results" in data:
                return data["results"][0]["latitude"], data["results"][0]["longitude"]
    return None, None

async def get_weather(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,precipitation_sum,windspeed_10m_max"
        f"&timezone=auto"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

def calculate_score(temp, wind, rain, activity):
    score = 100

    # Вітер
    if wind > 10:
        score -= 60
    elif wind > 7:
        score -= 30
    elif wind > 4:
        score -= 10

    # Дощ
    if rain > 5:
        score -= 60
    elif rain > 2:
        score -= 30
    elif rain > 0:
        score -= 10

    # Температура
    if temp < 5 or temp > 30:
        score -= 40
    elif temp < 10 or temp > 25:
        score -= 15

    # Додатковий штраф для велосипеда
    if activity == "🚴 Велосипед" and wind > 7:
        score -= 15

    return max(score, 0)

@dp.message()
async def handle_city(message: types.Message):
    city = message.text

    lat, lon = await get_coordinates(city)
    if not lat:
        await message.answer("Місто не знайдено. Спробуй іншу назву.")
        return

    weather = await get_weather(lat, lon)

    daily = weather["daily"]
    dates = daily["time"]
    temps = daily["temperature_2m_max"]
    winds = daily["windspeed_10m_max"]
    rains = daily["precipitation_sum"]

    response_text = f"📍 {city}\n\n"

    for i in range(3):
        score = calculate_score(temps[i], winds[i], rains[i], "🚴 Велосипед")
        response_text += (
            f"📅 {dates[i]}\n"
            f"Темп: {temps[i]}°C\n"
            f"Вітер: {winds[i]} м/с\n"
            f"Дощ: {rains[i]} мм\n"
            f"Оцінка: {score}/100\n\n"
        )

    await message.answer(response_text)
    await message.answer("Обери активність:", reply_markup=activities_keyboard)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
