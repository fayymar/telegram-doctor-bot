import re
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states import Registration, EditProfile
from bot.keyboards import (
    get_main_menu, get_phone_keyboard, get_gender_keyboard, 
    get_skip_keyboard, get_profile_menu, get_edit_profile_menu
)
from database.connection import supabase_client
from database.models import UserProfile


router = Router()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def parse_birthdate_flexible(text: str) -> datetime | None:
    """
    Гибкий парсинг даты рождения
    Принимает различные форматы: ДД.ММ.ГГГГ, ДД/ММ/ГГГГ, ДД-ММ-ГГГГ, ДД ММ ГГГГ
    
    Args:
        text: Текст с датой
    
    Returns:
        datetime объект или None если не удалось распарсить
    """
    # Убираем лишние пробелы
    text = text.strip()
    
    # Список возможных форматов
    formats = [
        r'(\d{1,2})[.\s/-](\d{1,2})[.\s/-](\d{4})',  # ДД.ММ.ГГГГ, ДД ММ ГГГГ и т.д.
        r'(\d{4})[.\s/-](\d{1,2})[.\s/-](\d{1,2})',  # ГГГГ.ММ.ДД
    ]
    
    for pattern in formats:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            
            # Определяем порядок (день, месяц, год)
            if len(groups[0]) == 4:  # Год впереди
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            else:  # День впереди
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            
            # Проверяем валидность
            try:
                date = datetime(year, month, day)
                
                # Проверяем разумность даты (от 1900 года до сегодня)
                if 1900 <= year <= datetime.now().year:
                    # Проверяем что человеку от 0 до 120 лет
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
    
    # Базовая валидация (минимум 2 слова)
    if len(full_name.split()) < 2:
        await message.answer(
            "❌ Пожалуйста, введите полное ФИО (минимум имя и фамилию)\n"
            "Например: Иван Петров или Петров Иван Сергеевич"
        )
        return
    
    await state.update_data(full_name=full_name)
    await message.answer(
        "📱 *Номер телефона*\n\n"
        "Поделитесь номером телефона для связи с клиникой.\n"
        "Можете пропустить этот шаг.",
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


@router.message(Registration.waiting_for_phone, F.text == "⏭ Пропустить")
async def skip_phone(message: Message, state: FSMContext):
    """Пропуск номера телефона"""
    await state.update_data(phone=None)
    
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
    
    # Простая валидация (только цифры, + и пробелы)
    if not re.match(r'^[\d\s\+\-\(\)]+$', phone):
        await message.answer(
            "❌ Некорректный номер телефона\n"
            "Используйте кнопку 'Поделиться номером' или пропустите этот шаг."
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


@router.callback_query(Registration.waiting_for_gender, F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    gender = callback.data.split("_")[1]  # male или female
    await state.update_data(gender=gender)
    
    gender_emoji = "👨" if gender == "male" else "👩"
    
    await callback.message.edit_text(
        f"{gender_emoji} Пол: {'Мужской' if gender == 'male' else 'Женский'}"
    )
    
    await callback.message.answer(
        "📏 *Рост (в см)*\n\n"
        "Введите ваш рост или пропустите.",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_height)
    await callback.answer()


@router.message(Registration.waiting_for_height, F.text == "⏭ Пропустить")
async def skip_height(message: Message, state: FSMContext):
    """Пропуск роста"""
    await state.update_data(height=None)
    
    await message.answer(
        "⚖️ *Вес (в кг)*\n\n"
        "Введите ваш вес или пропустите.",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_weight)


@router.message(Registration.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    try:
        height = int(message.text.strip())
        if 50 <= height <= 250:
            await state.update_data(height=height)
            await message.answer(
                "⚖️ *Вес (в кг)*\n\n"
                "Введите ваш вес или пропустите.",
                reply_markup=get_skip_keyboard(),
                parse_mode="Markdown"
            )
            await state.set_state(Registration.waiting_for_weight)
        else:
            await message.answer("❌ Рост должен быть от 50 до 250 см")
    except ValueError:
        await message.answer("❌ Введите число")


@router.message(Registration.waiting_for_weight, F.text == "⏭ Пропустить")
async def skip_weight(message: Message, state: FSMContext):
    """Пропуск веса и завершение регистрации"""
    await state.update_data(weight=None)
    await finish_registration(message, state)


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
    
    # Сохраняем в БД
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
    
    # Формируем текст профиля
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

@router.callback_query(F.data == "edit_profile")
async def start_edit_profile(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования профиля"""
    await callback.message.edit_text(
        "✏️ *Редактирование профиля*\n\n"
        "Выберите поле для изменения:",
        reply_markup=get_edit_profile_menu(),
        parse_mode="Markdown"
    )
    await state.set_state(EditProfile.choosing_field)
    await callback.answer()


@router.callback_query(EditProfile.choosing_field, F.data.startswith("edit_"))
async def choose_field_to_edit(callback: CallbackQuery, state: FSMContext):
    """Выбор поля для редактирования"""
    field = callback.data.split("_", 1)[1]
    
    prompts = {
        "full_name": "👤 Введите новое ФИО:",
        "phone": "📱 Введите новый номер телефона:",
        "birthdate": "🎂 Введите новую дату рождения (в любом формате):",
        "gender": "⚧️ Выберите пол:",
        "height": "📏 Введите новый рост (в см):",
        "weight": "⚖️ Введите новый вес (в кг):"
    }
    
    await state.update_data(editing_field=field)
    
    if field == "gender":
        await callback.message.edit_text(
            prompts[field],
            reply_markup=get_gender_keyboard()
        )
        await state.set_state(EditProfile.waiting_for_gender)
    else:
        await callback.message.edit_text(prompts[field])
        await state.set_state(getattr(EditProfile, f"waiting_for_{field}"))
    
    await callback.answer()


# Обработчики для каждого поля (аналогично регистрации)

@router.message(EditProfile.waiting_for_full_name)
async def edit_full_name(message: Message, state: FSMContext):
    """Редактирование ФИО"""
    full_name = message.text.strip()
    
    if len(full_name.split()) < 2:
        await message.answer("❌ Введите полное ФИО (минимум имя и фамилию)")
        return
    
    await update_user_profile(message.from_user.id, {'full_name': full_name})
    await message.answer(
        f"✅ ФИО обновлено: {full_name}",
        reply_markup=get_main_menu()
    )
    await state.clear()


@router.message(EditProfile.waiting_for_phone)
async def edit_phone(message: Message, state: FSMContext):
    """Редактирование телефона"""
    phone = message.text.strip()
    
    if not re.match(r'^[\d\s\+\-\(\)]+$', phone):
        await message.answer("❌ Некорректный номер телефона")
        return
    
    await update_user_profile(message.from_user.id, {'phone': phone})
    await message.answer(
        f"✅ Телефон обновлен: {phone}",
        reply_markup=get_main_menu()
    )
    await state.clear()


@router.message(EditProfile.waiting_for_birthdate)
async def edit_birthdate(message: Message, state: FSMContext):
    """Редактирование даты рождения"""
    birthdate = parse_birthdate_flexible(message.text)
    
    if not birthdate:
        await message.answer("❌ Не удалось распознать дату")
        return
    
    await update_user_profile(message.from_user.id, {
        'birthdate': birthdate.strftime('%Y-%m-%d')
    })
    
    age = calculate_age(birthdate)
    await message.answer(
        f"✅ Дата рождения обновлена\nВаш возраст: {age} лет",
        reply_markup=get_main_menu()
    )
    await state.clear()


@router.callback_query(EditProfile.waiting_for_gender, F.data.startswith("gender_"))
async def edit_gender(callback: CallbackQuery, state: FSMContext):
    """Редактирование пола"""
    gender = callback.data.split("_")[1]
    
    await update_user_profile(callback.from_user.id, {'gender': gender})
    
    gender_text = "Мужской" if gender == "male" else "Женский"
    await callback.message.edit_text(f"✅ Пол обновлен: {gender_text}")
    await callback.message.answer("Возвращаемся в главное меню", reply_markup=get_main_menu())
    await state.clear()
    await callback.answer()


@router.message(EditProfile.waiting_for_height)
async def edit_height(message: Message, state: FSMContext):
    """Редактирование роста"""
    try:
        height = int(message.text.strip())
        if 50 <= height <= 250:
            await update_user_profile(message.from_user.id, {'height': height})
            await message.answer(
                f"✅ Рост обновлен: {height} см",
                reply_markup=get_main_menu()
            )
            await state.clear()
        else:
            await message.answer("❌ Рост должен быть от 50 до 250 см")
    except ValueError:
        await message.answer("❌ Введите число")


@router.message(EditProfile.waiting_for_weight)
async def edit_weight(message: Message, state: FSMContext):
    """Редактирование веса"""
    try:
        weight = float(message.text.strip().replace(',', '.'))
        if 20 <= weight <= 300:
            await update_user_profile(message.from_user.id, {'weight': weight})
            await message.answer(
                f"✅ Вес обновлен: {weight} кг",
                reply_markup=get_main_menu()
            )
            await state.clear()
        else:
            await message.answer("❌ Вес должен быть от 20 до 300 кг")
    except ValueError:
        await message.answer("❌ Введите число")


@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext):
    """Возврат к просмотру профиля"""
    await state.clear()
    profile = await get_user_profile(callback.from_user.id)
    
    age = calculate_age(datetime.fromisoformat(profile.birthdate)) if profile.birthdate else "не указан"
    gender_text = "Мужской" if profile.gender == "male" else "Женский"
    
    profile_text = f"👤 *Ваш профиль*\n\n"
    profile_text += f"ФИО: {profile.full_name or 'не указано'}\n"
    profile_text += f"Телефон: {profile.phone or 'не указан'}\n"
    profile_text += f"Возраст: {age} лет\n"
    profile_text += f"Пол: {gender_text}\n"
    profile_text += f"Рост: {profile.height or 'не указан'} см\n"
    profile_text += f"Вес: {profile.weight or 'не указан'} кг\n"
    
    await callback.message.edit_text(
        profile_text,
        reply_markup=get_profile_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.answer(
        "Главное меню",
        reply_markup=get_main_menu()
    )
    await callback.answer()
