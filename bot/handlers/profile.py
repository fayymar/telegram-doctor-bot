from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu_keyboard, gender_keyboard, skip_keyboard
from bot.states import RegistrationStates
from database.connection import db

router = Router()


# === Регистрация ===

@router.message(RegistrationStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    """Обработка возраста"""
    try:
        age = int(message.text)
        if age < 1 or age > 120:
            await message.answer("⚠️ Укажите корректный возраст от 1 до 120 лет:")
            return
        
        await db.update_user_profile(message.from_user.id, age=age)
        await message.answer(
            "Укажите ваш пол:",
            reply_markup=gender_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_gender)
        
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите возраст числом (например: 25)")


@router.message(RegistrationStates.waiting_for_gender)
async def process_gender(message: Message, state: FSMContext):
    """Обработка пола"""
    text = message.text.lower()
    
    if "мужской" in text or "муж" in text:
        gender = "male"
    elif "женский" in text or "жен" in text:
        gender = "female"
    elif "другой" in text or "друг" in text:
        gender = "other"
    else:
        await message.answer(
            "⚠️ Пожалуйста, выберите пол используя кнопки:",
            reply_markup=gender_keyboard()
        )
        return
    
    await db.update_user_profile(message.from_user.id, gender=gender)
    await message.answer(
        "Укажите ваш рост в сантиметрах (например: 175):",
        reply_markup=skip_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_height)


@router.message(RegistrationStates.waiting_for_height, F.text == "⏭️ Пропустить")
async def skip_height(message: Message, state: FSMContext):
    """Пропуск роста"""
    await message.answer(
        "Укажите ваш вес в килограммах (например: 70):",
        reply_markup=skip_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_weight)


@router.message(RegistrationStates.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    try:
        height = int(message.text)
        if height < 50 or height > 250:
            await message.answer("⚠️ Укажите корректный рост от 50 до 250 см:")
            return
        
        await db.update_user_profile(message.from_user.id, height=height)
        await message.answer(
            "Укажите ваш вес в килограммах (например: 70):",
            reply_markup=skip_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_weight)
        
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите рост числом в сантиметрах (например: 175)")


@router.message(RegistrationStates.waiting_for_weight, F.text == "⏭️ Пропустить")
async def skip_weight(message: Message, state: FSMContext):
    """Пропуск веса"""
    await state.clear()
    await message.answer(
        "✅ Регистрация завершена!\n\n"
        "Теперь вы можете начать консультацию, описав свои симптомы.",
        reply_markup=main_menu_keyboard()
    )


@router.message(RegistrationStates.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    try:
        weight = float(message.text.replace(',', '.'))
        if weight < 20 or weight > 300:
            await message.answer("⚠️ Укажите корректный вес от 20 до 300 кг:")
            return
        
        await db.update_user_profile(message.from_user.id, weight=weight)
        await state.clear()
        await message.answer(
            "✅ Регистрация завершена!\n\n"
            "Теперь вы можете начать консультацию, описав свои симптомы.",
            reply_markup=main_menu_keyboard()
        )
        
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите вес числом (например: 70 или 65.5)")


# === Просмотр и редактирование профиля ===

@router.message(F.text == "👤 Мой профиль")
async def view_profile(message: Message):
    """Просмотр профиля"""
    profile = await db.get_user_profile(message.from_user.id)
    
    if not profile:
        await message.answer("❌ Профиль не найден. Используйте /start для регистрации.")
        return
    
    gender_map = {
        "male": "Мужской",
        "female": "Женский",
        "other": "Другой"
    }
    
    profile_text = "👤 <b>Ваш профиль:</b>\n\n"
    
    if profile.get("age"):
        profile_text += f"📅 Возраст: {profile['age']} лет\n"
    if profile.get("gender"):
        profile_text += f"⚧ Пол: {gender_map.get(profile['gender'], 'Не указан')}\n"
    if profile.get("height"):
        profile_text += f"📏 Рост: {profile['height']} см\n"
    if profile.get("weight"):
        profile_text += f"⚖️ Вес: {profile['weight']} кг\n"
    
    profile_text += "\n<i>Для изменения данных используйте /start</i>"
    
    await message.answer(profile_text, parse_mode="HTML")
