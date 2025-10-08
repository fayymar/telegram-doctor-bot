from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from datetime import datetime

from bot.keyboards import main_menu_keyboard, gender_keyboard, skip_keyboard, phone_keyboard
from bot.states import RegistrationStates
from database.connection import db

router = Router()


# === РЕГИСТРАЦИЯ ===

# Этап 1: ФИО
@router.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    """Обработка ФИО"""
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("⚠️ Пожалуйста, укажите ваше полное имя (минимум 2 символа):")
        return
    
    full_name = message.text.strip()
    await db.update_user_profile(message.from_user.id, full_name=full_name)
    
    await message.answer(
        f"👤 Приятно познакомиться, {full_name.split()[0]}!\n\n"
        "📱 Теперь поделитесь номером телефона для связи:",
        reply_markup=phone_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_phone)


# Этап 2: Телефон
@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Обработка номера через кнопку"""
    phone = message.contact.phone_number
    
    # Форматируем номер
    if not phone.startswith('+'):
        phone = '+' + phone
    
    await db.update_user_profile(message.from_user.id, phone=phone)
    
    await message.answer(
        f"📱 Номер сохранён: {phone}\n\n"
        "📅 Укажите вашу дату рождения (в формате ДД.ММ.ГГГГ):\n"
        "<i>Например: 15.03.1990</i>",
        reply_markup=skip_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_birthdate)


@router.message(RegistrationStates.waiting_for_phone, F.text == "⏭️ Пропустить")
async def skip_phone(message: Message, state: FSMContext):
    """Пропуск номера телефона"""
    await message.answer(
        "📅 Укажите вашу дату рождения (в формате ДД.ММ.ГГГГ):\n"
        "<i>Например: 15.03.1990</i>",
        reply_markup=skip_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_birthdate)


@router.message(RegistrationStates.waiting_for_phone)
async def process_phone_text(message: Message, state: FSMContext):
    """Если пользователь ввёл телефон текстом"""
    if not message.text:
        await message.answer(
            "⚠️ Нажмите кнопку '📱 Поделиться номером' или 'Пропустить'",
            reply_markup=phone_keyboard()
        )
        return
    
    # Простая валидация
    phone = message.text.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    if len(phone) < 10:
        await message.answer(
            "⚠️ Номер телефона слишком короткий. Попробуйте ещё раз или нажмите 'Пропустить':",
            reply_markup=phone_keyboard()
        )
        return
    
    if not phone.startswith('+'):
        phone = '+' + phone
    
    await db.update_user_profile(message.from_user.id, phone=phone)
    
    await message.answer(
        f"📱 Номер сохранён: {phone}\n\n"
        "📅 Укажите вашу дату рождения (в формате ДД.ММ.ГГГГ):\n"
        "<i>Например: 15.03.1990</i>",
        reply_markup=skip_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_birthdate)


# Этап 3: Дата рождения
@router.message(RegistrationStates.waiting_for_birthdate, F.text == "⏭️ Пропустить")
async def skip_birthdate(message: Message, state: FSMContext):
    """Пропуск даты рождения"""
    await message.answer(
        "Укажите ваш пол:",
        reply_markup=gender_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_gender)


@router.message(RegistrationStates.waiting_for_birthdate)
async def process_birthdate(message: Message, state: FSMContext):
    """Обработка даты рождения"""
    if not message.text:
        await message.answer("⚠️ Пожалуйста, укажите дату рождения или нажмите 'Пропустить'")
        return
    
    # Парсинг даты
    date_str = message.text.strip()
    
    try:
        # Пробуем разные форматы
        for fmt in ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
            try:
                birthdate = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise ValueError("Неподдерживаемый формат")
        
        # Проверка на адекватность
        today = datetime.now().date()
        age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
        
        if age < 0 or age > 120:
            await message.answer(
                "⚠️ Некорректная дата рождения. Пожалуйста, укажите правильную дату (ДД.ММ.ГГГГ):"
            )
            return
        
        # Сохраняем
        await db.update_user_profile(message.from_user.id, birthdate=birthdate.isoformat())
        
        await message.answer(
            f"📅 Дата рождения сохранена: {birthdate.strftime('%d.%m.%Y')} (возраст: {age} лет)\n\n"
            "Укажите ваш пол:",
            reply_markup=gender_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_gender)
        
    except (ValueError, AttributeError):
        await message.answer(
            "⚠️ Неверный формат даты. Используйте формат ДД.ММ.ГГГГ\n"
            "<i>Например: 15.03.1990</i>",
            parse_mode="HTML"
        )


# Этап 4: Пол
@router.message(RegistrationStates.waiting_for_gender)
async def process_gender(message: Message, state: FSMContext):
    """Обработка пола"""
    text = message.text.lower()
    
    if "мужской" in text or "муж" in text:
        gender = "male"
    elif "женский" in text or "жен" in text:
        gender = "female"
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


# Этап 5: Рост
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


# Этап 6: Вес
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


# === ПРОСМОТР ПРОФИЛЯ ===

@router.message(F.text == "👤 Мой профиль")
async def view_profile(message: Message):
    """Просмотр профиля"""
    profile = await db.get_user_profile(message.from_user.id)
    
    if not profile:
        await message.answer("❌ Профиль не найден. Используйте /start для регистрации.")
        return
    
    gender_map = {
        "male": "Мужской",
        "female": "Женский"
    }
    
    profile_text = "👤 <b>Ваш профиль:</b>\n\n"
    
    if profile.get("full_name"):
        profile_text += f"📝 ФИО: {profile['full_name']}\n"
    if profile.get("phone"):
        profile_text += f"📱 Телефон: {profile['phone']}\n"
    if profile.get("birthdate"):
        try:
            birthdate = datetime.fromisoformat(profile['birthdate']).date()
            today = datetime.now().date()
            age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
            profile_text += f"📅 Дата рождения: {birthdate.strftime('%d.%m.%Y')} ({age} лет)\n"
        except:
            profile_text += f"📅 Дата рождения: {profile['birthdate']}\n"
    if profile.get("gender"):
        profile_text += f"⚧ Пол: {gender_map.get(profile['gender'], 'Не указан')}\n"
    if profile.get("height"):
        profile_text += f"📏 Рост: {profile['height']} см\n"
    if profile.get("weight"):
        profile_text += f"⚖️ Вес: {profile['weight']} кг\n"
    
    profile_text += "\n<i>Для изменения данных используйте /start</i>"
    
    await message.answer(profile_text, parse_mode="HTML")
