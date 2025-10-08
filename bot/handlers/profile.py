import re
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states import Registration, EditProfile
from bot.keyboards import (
    get_main_menu, get_phone_keyboard, get_gender_keyboard, 
    get_cancel_keyboard, get_profile_menu, get_edit_profile_menu
)
from database.connection import supabase_client
from database.models import UserProfile


router = Router()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def parse_birthdate_flexible(text: str) -> datetime | None:
    """
    Гибкий парсинг даты рождения
    Принимает различные форматы: ДД.ММ.ГГГГ, ДД/ММ/ГГГГ, ДД-ММ-ГГГГ, ДД ММ ГГГГ
    """
    text = text.strip()
    
    formats = [
        r'(\d{1,2})[.\s/-](\d{1,2})[.\s/-](\d{4})',
        r'(\d{4})[.\s/-](\d{1,2})[.\s/-](\d{1,2})',
    ]
    
    for pattern in formats:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            
            if len(groups[0]) == 4:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            
            try:
                date = datetime(year, month, day)
                
                if 1900 <= year <= datetime.now().year:
                    age = (datetime.now() - date).days // 365
                    if 0 <= age <= 120:
                        return date
            except ValueError:
                continue
    
    return None


def calculate_age(birthdate: datetime) -> int:
    """Вычисляет возраст по дате рождения"""
    today = datetime.now()
    age = today.year - birthdate.year
    if (today.month, today.day) < (birthdate.month, birthdate.day):
        age -= 1
    return age


async def get_user_profile(user_id: int) -> UserProfile | None:
    """Получает профиль пользователя из БД"""
    try:
        response = supabase_client.table('user_profiles').select('*').eq('user_id', user_id).execute()
        if response.data:
            return UserProfile(**response.data[0])
    except Exception as e:
        print(f"DB Error: {e}")
    return None


async def update_user_profile(user_id: int, data: dict):
    """Обновляет профиль пользователя в БД"""
    try:
        data['updated_at'] = datetime.now().isoformat()
        supabase_client.table('user_profiles').upsert({
            'user_id': user_id,
            **data
        }).execute()
    except Exception as e:
        print(f"DB Error: {e}")


# ============ РЕГИСТРАЦИЯ ============

@router.message(Registration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    """Обработка ФИО"""
    full_name = message.text.strip()
    
    if len(full_name.split()) < 2:
        await message.answer(
            "❌ Пожалуйста, введите полное ФИО (минимум имя и фамилию)\n"
            "Например: Иван Петров или Петров Иван Сергеевич"
        )
        return
    
    await state.update_data(full_name=full_name)
    await message.answer(
        "📱 *Номер телефона*\n\n"
        "Поделитесь номером телефона для связи с клиникой.",
        reply_markup=get_phone_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_phone)


@router.message(Registration.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Обработка номера через контакт"""
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    
    await message.answer(
        "🎂 *Дата рождения*\n\n"
        "Введите дату рождения в любом формате:\n"
        "• 15.05.1990\n"
        "• 15/05/1990\n"
        "• 15 05 1990\n"
        "• 1990-05-15",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_birthdate)


@router.message(Registration.waiting_for_phone)
async def process_phone_text(message: Message, state: FSMContext):
    """Обработка номера текстом"""
    phone = message.text.strip()
    
    if not re.match(r'^[\d\s\+\-\(\)]+$', phone):
        await message.answer(
            "❌ Некорректный номер телефона\n"
            "Используйте кнопку 'Поделиться номером'."
        )
        return
    
    await state.update_data(phone=phone)
    await message.answer(
        "🎂 *Дата рождения*\n\n"
        "Введите дату рождения в любом формате:\n"
        "• 15.05.1990\n"
        "• 15/05/1990\n"
        "• 15 05 1990\n"
        "• 1990-05-15",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_birthdate)


@router.message(Registration.waiting_for_birthdate)
async def process_birthdate(message: Message, state: FSMContext):
    """Обработка даты рождения"""
    birthdate = parse_birthdate_flexible(message.text)
    
    if not birthdate:
        await message.answer(
            "❌ Не удалось распознать дату\n\n"
            "Попробуйте один из форматов:\n"
            "• 15.05.1990\n"
            "• 15/05/1990\n"
            "• 15 05 1990\n"
            "• 1990-05-15"
        )
        return
    
    age = calculate_age(birthdate)
    await state.update_data(birthdate=birthdate.strftime('%Y-%m-%d'))
    
    await message.answer(
        f"⚧️ *Пол*\n\n"
        f"Ваш возраст: {age} лет\n"
        f"Выберите пол:",
        reply_markup=get_gender_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_gender)


@router.message(Registration.waiting_for_gender, F.text.in_(["👨 Мужской", "👩 Женский"]))
async def process_gender(message: Message, state: FSMContext):
    """Обработка выбора пола"""
    gender = "male" if message.text == "👨 Мужской" else "female"
    await state.update_data(gender=gender)
    
    await message.answer(
        "📏 *Рост (в см)*\n\n"
        "Введите ваш рост:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_height)


@router.message(Registration.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    try:
        height = int(message.text.strip())
        if 50 <= height <= 250:
            await state.update_data(height=height)
            await message.answer(
                "⚖️ *Вес (в кг)*\n\n"
                "Введите ваш вес:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
            await state.set_state(Registration.waiting_for_weight)
        else:
            await message.answer("❌ Рост должен быть от 50 до 250 см")
    except ValueError:
        await message.answer("❌ Введите число")


@router.message(Registration.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    try:
        weight = float(message.text.strip().replace(',', '.'))
        if 20 <= weight <= 300:
            await state.update_data(weight=weight)
            await finish_registration(message, state)
        else:
            await message.answer("❌ Вес должен быть от 20 до 300 кг")
    except ValueError:
        await message.answer("❌ Введите число")


async def finish_registration(message: Message, state: FSMContext):
    """Завершение регистрации"""
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username
    
    await update_user_profile(user_id, {
        'username': username,
        'full_name': data.get('full_name'),
        'phone': data.get('phone'),
        'birthdate': data.get('birthdate'),
        'gender': data.get('gender'),
        'height': data.get('height'),
        'weight': data.get('weight')
    })
    
    await state.clear()
    
    await message.answer(
        "✅ *Регистрация завершена!*\n\n"
        "Теперь вы можете:\n"
        "• Начать консультацию\n"
        "• Найти специалиста\n"
        "• Просмотреть профиль",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )


# ============ ПРОСМОТР ПРОФИЛЯ ============

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    """Показывает профиль пользователя"""
    profile = await get_user_profile(message.from_user.id)
    
    if not profile:
        await message.answer(
            "❌ Профиль не найден\n"
            "Используйте /start для регистрации"
        )
        return
    
    age = calculate_age(datetime.fromisoformat(profile.birthdate)) if profile.birthdate else "не указан"
    gender_text = "Мужской" if profile.gender == "male" else "Женский"
    
    profile_text = f"👤 *Ваш профиль*\n\n"
    profile_text += f"ФИО: {profile.full_name or 'не указано'}\n"
    profile_text += f"Телефон: {profile.phone or 'не указан'}\n"
    profile_text += f"Возраст: {age} лет\n"
    profile_text += f"Пол: {gender_text}\n"
    profile_text += f"Рост: {profile.height or 'не указан'} см\n"
    profile_text += f"Вес: {profile.weight or 'не указан'} кг\n"
    
    await message.answer(
        profile_text,
        reply_markup=get_profile_menu(),
        parse_mode="Markdown"
    )


# ============ РЕДАКТИРОВАНИЕ ПРОФИЛЯ ============

@router.message(F.text == "✏️ Изменить данные")
async def start_edit_profile(message: Message, state: FSMContext):
    """Начало редактирования профиля"""
    await message.answer(
        "✏️ *Редактирование профиля*\n\n"
        "Выберите поле для изменения:",
        reply_markup=get_edit_profile_menu(),
        parse_mode="Markdown"
    )
    await state.set_state(EditProfile.choosing_field)


@router.message(EditProfile.choosing_field, F.text.in_([
    "👤 ФИО", "📱 Телефон", "🎂 Дата рождения", "⚧️ Пол", "📏 Рост", "⚖️ Вес"
]))
async def choose_field_to_edit(message: Message, state: FSMContext):
    """Выбор поля для редактирования"""
    field_map = {
        "👤 ФИО": ("full_name", "👤 Введите новое ФИО:"),
        "📱 Телефон": ("phone", "📱 Введите новый номер телефона:"),
        "🎂 Дата рождения": ("birthdate", "🎂 Введите новую дату рождения:"),
        "⚧️ Пол": ("gender", "⚧️ Выберите пол:"),
        "📏 Рост": ("height", "📏 Введите новый рост (в см):"),
        "⚖️ Вес": ("weight", "⚖️ Введите новый вес (в кг):")
    }
    
    field, prompt = field_map[message.text]
    await state.update_data(editing_field=field)
    
    if field == "gender":
        await message.answer(prompt, reply_markup=get_gender_keyboard())
    else:
        await message.answer(prompt, reply_markup=get_cancel_keyboard())
    
    await state.set_state(getattr(EditProfile, f"waiting_for_{field}"))


# Обработчики для каждого поля

@router.message(EditProfile.waiting_for_full_name)
async def edit_full_name(message: Message, state: FSMContext):
    full_name = message.text.strip()
    if len(full_name.split()) < 2:
        await message.answer("❌ Введите полное ФИО")
        return
    
    await update_user_profile(message.from_user.id, {'full_name': full_name})
    await message.answer(f"✅ ФИО обновлено: {full_name}", reply_markup=get_main_menu())
    await state.clear()


@router.message(EditProfile.waiting_for_phone)
async def edit_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not re.match(r'^[\d\s\+\-\(\)]+$', phone):
        await message.answer("❌ Некорректный номер")
        return
    
    await update_user_profile(message.from_user.id, {'phone': phone})
    await message.answer(f"✅ Телефон обновлен: {phone}", reply_markup=get_main_menu())
    await state.clear()


@router.message(EditProfile.waiting_for_birthdate)
async def edit_birthdate(message: Message, state: FSMContext):
    birthdate = parse_birthdate_flexible(message.text)
    if not birthdate:
        await message.answer("❌ Не удалось распознать дату")
        return
    
    await update_user_profile(message.from_user.id, {'birthdate': birthdate.strftime('%Y-%m-%d')})
    age = calculate_age(birthdate)
    await message.answer(f"✅ Дата рождения обновлена\nВаш возраст: {age} лет", reply_markup=get_main_menu())
    await state.clear()


@router.message(EditProfile.waiting_for_gender, F.text.in_(["👨 Мужской", "👩 Женский"]))
async def edit_gender(message: Message, state: FSMContext):
    gender = "male" if message.text == "👨 Мужской" else "female"
    await update_user_profile(message.from_user.id, {'gender': gender})
    
    gender_text = "Мужской" if gender == "male" else "Женский"
    await message.answer(f"✅ Пол обновлен: {gender_text}", reply_markup=get_main_menu())
    await state.clear()


@router.message(EditProfile.waiting_for_height)
async def edit_height(message: Message, state: FSMContext):
    try:
        height = int(message.text.strip())
        if 50 <= height <= 250:
            await update_user_profile(message.from_user.id, {'height': height})
            await message.answer(f"✅ Рост обновлен: {height} см", reply_markup=get_main_menu())
            await state.clear()
        else:
            await message.answer("❌ Рост должен быть от 50 до 250 см")
    except ValueError:
        await message.answer("❌ Введите число")


@router.message(EditProfile.waiting_for_weight)
async def edit_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.strip().replace(',', '.'))
        if 20 <= weight <= 300:
            await update_user_profile(message.from_user.id, {'weight': weight})
            await message.answer(f"✅ Вес обновлен: {weight} кг", reply_markup=get_main_menu())
            await state.clear()
        else:
            await message.answer("❌ Вес должен быть от 20 до 300 кг")
    except ValueError:
        await message.answer("❌ Введите число")


@router.message(F.text == "🔙 Назад к профилю")
async def back_to_profile(message: Message, state: FSMContext):
    """Возврат к просмотру профиля"""
    await state.clear()
    await show_profile(message)


@router.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await message.answer("Главное меню", reply_markup=get_main_menu())
