from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.states import Registration, EditProfile
from bot.keyboards import (
    get_main_menu,
    get_phone_keyboard,
    get_gender_keyboard,
    get_cancel_keyboard,
    get_profile_menu,
    get_edit_profile_menu
)
from database.connection import supabase_client
from services.phone_formatter import format_phone_number, get_phone_info


router = Router()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def parse_date(date_string: str) -> datetime:
    """
    Парсит дату в гибких форматах
    
    Поддерживаемые форматы:
    - ДД.ММ.ГГГГ (15.03.1990)
    - ДД/ММ/ГГГГ (15/03/1990)
    - ДД ММ ГГГГ (15 03 1990)
    """
    # Заменяем все разделители на точку
    normalized = date_string.replace("/", ".").replace(" ", ".")
    
    # Пробуем распарсить
    try:
        return datetime.strptime(normalized, "%d.%m.%Y")
    except ValueError:
        raise ValueError("Неверный формат даты")


# ============ РЕГИСТРАЦИЯ ============

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    """Показать профиль пользователя"""
    try:
        response = supabase_client.table('user_profiles').select('*').eq('user_id', message.from_user.id).execute()
        
        if not response.data:
            await message.answer(
                "❌ Профиль не найден\n\n"
                "Пожалуйста, пройдите регистрацию:\n"
                "Используйте /start"
            )
            return
        
        profile = response.data[0]
        
        # Форматируем дату рождения
        birthdate = profile.get('birthdate')
        age = None
        if birthdate:
            birthdate_obj = datetime.fromisoformat(birthdate)
            age = (datetime.now() - birthdate_obj).days // 365
            birthdate_formatted = birthdate_obj.strftime("%d.%m.%Y")
        else:
            birthdate_formatted = "не указано"
        
        # Форматируем пол
        gender = profile.get('gender')
        gender_text = {"male": "👨 Мужской", "female": "👩 Женский"}.get(gender, "не указано")
        
        # Формируем текст профиля
        profile_text = f"👤 *Ваш профиль*\n\n"
        profile_text += f"*ФИО:* {profile.get('full_name', 'не указано')}\n"
        profile_text += f"*Телефон:* {profile.get('phone', 'не указано')}\n"
        profile_text += f"*Дата рождения:* {birthdate_formatted}"
        
        if age:
            profile_text += f" ({age} лет)\n"
        else:
            profile_text += "\n"
        
        profile_text += f"*Пол:* {gender_text}\n"
        profile_text += f"*Рост:* {profile.get('height', 'не указано')} см\n"
        profile_text += f"*Вес:* {profile.get('weight', 'не указано')} кг"
        
        await message.answer(
            profile_text,
            reply_markup=get_profile_menu(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при загрузке профиля")


@router.message(F.text == "🔙 В главное меню")
async def back_to_main_from_profile(message: Message, state: FSMContext):
    """Возврат в главное меню из профиля"""
    await state.clear()
    await message.answer(
        "Главное меню",
        reply_markup=get_main_menu()
    )


# ============ ЭТАП 1: ФИО ============

@router.message(Registration.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext):
    """Обработка ФИО"""
    full_name = message.text.strip()
    
    # Базовая валидация
    if len(full_name) < 3:
        await message.answer("❌ ФИО слишком короткое. Попробуйте ещё раз:")
        return
    
    # Проверка на минимум 2 слова
    if len(full_name.split()) < 2:
        await message.answer(
            "❌ Пожалуйста, укажите хотя бы Фамилию и Имя\n"
            "Например: Иванов Иван"
        )
        return
    
    await state.update_data(full_name=full_name)
    
    await message.answer(
        f"✅ ФИО: {full_name}",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await message.answer(
        "📱 *Шаг 2 из 6*\n\n"
        "Поделитесь номером телефона\n\n"
        "Вы можете:\n"
        "• Нажать кнопку ниже\n"
        "• Ввести номер вручную (в любом формате)\n\n"
        "Примеры:\n"
        "• +998 90 123 45 67\n"
        "• 998901234567\n"
        "• 90 123 45 67",
        reply_markup=get_phone_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Registration.waiting_for_phone)


# ============ ЭТАП 2: ТЕЛЕФОН ============

@router.message(Registration.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Обработка номера через кнопку 'Поделиться номером'"""
    phone = message.contact.phone_number
    
    # Форматируем номер
    success, formatted_phone, error = format_phone_number(phone)
    
    if not success:
        await message.answer(
            f"{error}\n\n"
            "Попробуйте ввести номер вручную в формате:\n"
            "• +998 90 123 45 67 (Узбекистан)\n"
            "• +7 900 123 45 67 (Россия)\n"
            "• +1 555 123 4567 (США)"
        )
        return
    
    # Получаем дополнительную информацию
    phone_info = get_phone_info(phone)
    
    await state.update_data(phone=formatted_phone)
    
    # Красиво показываем сохранённый номер
    info_text = f"✅ *Телефон сохранён:*\n\n"
    info_text += f"📱 {formatted_phone}\n"
    if phone_info.get('valid'):
        info_text += f"🌍 {phone_info.get('country_name')} ({phone_info.get('country_code')})\n"
        info_text += f"📞 Тип: {phone_info.get('number_type')}"
    
    await message.answer(info_text, reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    
    # Переход к следующему этапу
    await message.answer(
        "🎂 *Шаг 3 из 6*\n\n"
        "Введите дату рождения\n\n"
        "Формат: ДД.ММ.ГГГГ (например, 15.03.1990)\n"
        "Также принимается: 15/03/1990 или 15 03 1990",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Registration.waiting_for_birthdate)


@router.message(Registration.waiting_for_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    """Обработка номера введённого текстом"""
    phone_input = message.text.strip()
    
    # Форматируем номер
    success, formatted_phone, error = format_phone_number(phone_input)
    
    if not success:
        await message.answer(
            f"{error}\n\n"
            "Примеры правильных форматов:\n"
            "• +998 90 123 45 67 (Узбекистан)\n"
            "• +7 900 123 45 67 (Россия)\n"
            "• +1 555 123 4567 (США)\n"
            "• 90 123 45 67 (для Узбекистана)\n\n"
            "Или нажмите кнопку 📱 Поделиться номером"
        )
        return
    
    # Получаем дополнительную информацию
    phone_info = get_phone_info(phone_input)
    
    await state.update_data(phone=formatted_phone)
    
    # Красиво показываем сохранённый номер
    info_text = f"✅ *Телефон сохранён:*\n\n"
    info_text += f"📱 {formatted_phone}\n"
    if phone_info.get('valid'):
        info_text += f"🌍 {phone_info.get('country_name')} ({phone_info.get('country_code')})\n"
        info_text += f"📞 Тип: {phone_info.get('number_type')}"
    
    await message.answer(info_text, reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    
    # Переход к следующему этапу
    await message.answer(
        "🎂 *Шаг 3 из 6*\n\n"
        "Введите дату рождения\n\n"
        "Формат: ДД.ММ.ГГГГ (например, 15.03.1990)\n"
        "Также принимается: 15/03/1990 или 15 03 1990",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Registration.waiting_for_birthdate)


# ============ ЭТАП 3: ДАТА РОЖДЕНИЯ ============

@router.message(Registration.waiting_for_birthdate, F.text)
async def process_birthdate(message: Message, state: FSMContext):
    """Обработка даты рождения"""
    date_string = message.text.strip()
    
    try:
        birthdate = parse_date(date_string)
        
        # Проверка на адекватность даты
        if birthdate > datetime.now():
            await message.answer("❌ Дата рождения не может быть в будущем")
            return
        
        age = (datetime.now() - birthdate).days // 365
        
        if age < 1 or age > 120:
            await message.answer("❌ Пожалуйста, укажите корректную дату рождения")
            return
        
        await state.update_data(birthdate=birthdate.date().isoformat())
        
        await message.answer(
            f"✅ Дата рождения: {birthdate.strftime('%d.%m.%Y')} ({age} лет)",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await message.answer(
            "⚧️ *Шаг 4 из 6*\n\n"
            "Выберите пол:",
            reply_markup=get_gender_keyboard(),
            parse_mode="Markdown"
        )
        
        await state.set_state(Registration.waiting_for_gender)
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты\n\n"
            "Используйте формат: ДД.ММ.ГГГГ\n"
            "Например: 15.03.1990"
        )


# ============ ЭТАП 4: ПОЛ ============

@router.message(Registration.waiting_for_gender, F.text.in_(["👨 Мужской", "👩 Женский"]))
async def process_gender(message: Message, state: FSMContext):
    """Обработка выбора пола"""
    gender = "male" if message.text == "👨 Мужской" else "female"
    
    await state.update_data(gender=gender)
    
    await message.answer(
        f"✅ Пол: {message.text}",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await message.answer(
        "📏 *Шаг 5 из 6*\n\n"
        "Введите ваш рост в сантиметрах\n"
        "Например: 175",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Registration.waiting_for_height)


# ============ ЭТАП 5: РОСТ ============

@router.message(Registration.waiting_for_height, F.text)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    try:
        height = int(message.text.strip())
        
        if height < 50 or height > 250:
            await message.answer("❌ Пожалуйста, укажите корректный рост (50-250 см)")
            return
        
        await state.update_data(height=height)
        
        await message.answer(
            f"✅ Рост: {height} см",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await message.answer(
            "⚖️ *Шаг 6 из 6*\n\n"
            "Введите ваш вес в килограммах\n"
            "Например: 70",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        
        await state.set_state(Registration.waiting_for_weight)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например, 175)")


# ============ ЭТАП 6: ВЕС ============

@router.message(Registration.waiting_for_weight, F.text)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса и завершение регистрации"""
    try:
        weight = float(message.text.strip().replace(",", "."))
        
        if weight < 20 or weight > 300:
            await message.answer("❌ Пожалуйста, укажите корректный вес (20-300 кг)")
            return
        
        await state.update_data(weight=weight)
        
        await message.answer(
            f"✅ Вес: {weight} кг",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Сохраняем в базу данных
        data = await state.get_data()
        
        try:
            profile_data = {
                'user_id': message.from_user.id,
                'username': message.from_user.username,
                'full_name': data['full_name'],
                'phone': data['phone'],
                'birthdate': data['birthdate'],
                'gender': data['gender'],
                'height': data['height'],
                'weight': data['weight'],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            supabase_client.table('user_profiles').insert(profile_data).execute()
            
            await message.answer(
                "🎉 *Регистрация завершена!*\n\n"
                "Ваш профиль успешно создан.\n"
                "Теперь вы можете пользоваться всеми функциями бота!",
                reply_markup=get_main_menu(),
                parse_mode="Markdown"
            )
            
            await state.clear()
            
        except Exception as e:
            print(f"DB Error: {e}")
            await message.answer(
                "❌ Ошибка при сохранении профиля\n"
                "Попробуйте ещё раз: /start"
            )
            await state.clear()
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например, 70 или 70.5)")


# ============ РЕДАКТИРОВАНИЕ ПРОФИЛЯ ============

@router.message(F.text == "✏️ Изменить данные")
async def edit_profile_menu(message: Message, state: FSMContext):
    """Меню редактирования профиля"""
    await message.answer(
        "✏️ *Редактирование профиля*\n\n"
        "Что вы хотите изменить?",
        reply_markup=get_edit_profile_menu(),
        parse_mode="Markdown"
    )
    
    await state.set_state(EditProfile.choosing_field)


@router.message(F.text == "🔙 Назад к профилю")
async def back_to_profile(message: Message, state: FSMContext):
    """Возврат к профилю"""
    await state.clear()
    await show_profile(message)


# ============ ВЫБОР ПОЛЯ ДЛЯ РЕДАКТИРОВАНИЯ ============

@router.message(EditProfile.choosing_field, F.text == "👤 ФИО")
async def edit_full_name_start(message: Message, state: FSMContext):
    """Начало редактирования ФИО"""
    await message.answer(
        "👤 Введите новое ФИО:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_full_name)


@router.message(EditProfile.choosing_field, F.text == "📱 Телефон")
async def edit_phone_start(message: Message, state: FSMContext):
    """Начало редактирования телефона"""
    await message.answer(
        "📱 Введите новый номер телефона\n\n"
        "Примеры форматов:\n"
        "• +998 90 123 45 67\n"
        "• +7 900 123 45 67\n"
        "• 90 123 45 67",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_phone)


@router.message(EditProfile.choosing_field, F.text == "🎂 Дата рождения")
async def edit_birthdate_start(message: Message, state: FSMContext):
    """Начало редактирования даты рождения"""
    await message.answer(
        "🎂 Введите новую дату рождения\n\n"
        "Формат: ДД.ММ.ГГГГ (например, 15.03.1990)",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_birthdate)


@router.message(EditProfile.choosing_field, F.text == "⚧️ Пол")
async def edit_gender_start(message: Message, state: FSMContext):
    """Начало редактирования пола"""
    await message.answer(
        "⚧️ Выберите пол:",
        reply_markup=get_gender_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_gender)


@router.message(EditProfile.choosing_field, F.text == "📏 Рост")
async def edit_height_start(message: Message, state: FSMContext):
    """Начало редактирования роста"""
    await message.answer(
        "📏 Введите новый рост (в см):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_height)


@router.message(EditProfile.choosing_field, F.text == "⚖️ Вес")
async def edit_weight_start(message: Message, state: FSMContext):
    """Начало редактирования веса"""
    await message.answer(
        "⚖️ Введите новый вес (в кг):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_weight)


# ============ ОБРАБОТКА РЕДАКТИРОВАНИЯ ============

@router.message(EditProfile.waiting_for_full_name, F.text)
async def edit_full_name(message: Message, state: FSMContext):
    """Обработка редактирования ФИО"""
    full_name = message.text.strip()
    
    if len(full_name) < 3 or len(full_name.split()) < 2:
        await message.answer("❌ Укажите хотя бы Фамилию и Имя")
        return
    
    try:
        supabase_client.table('user_profiles').update({
            'full_name': full_name,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', message.from_user.id).execute()
        
        await message.answer(f"✅ ФИО обновлено: {full_name}")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)
        
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_phone, F.text)
async def edit_phone(message: Message, state: FSMContext):
    """Обработка редактирования телефона"""
    phone_input = message.text.strip()
    
    # Форматируем номер
    success, formatted_phone, error = format_phone_number(phone_input)
    
    if not success:
        await message.answer(
            f"{error}\n\n"
            "Попробуйте ещё раз:"
        )
        return
    
    try:
        # Получаем информацию для красивого отображения
        phone_info = get_phone_info(phone_input)
        
        # Сохраняем в БД
        supabase_client.table('user_profiles').update({
            'phone': formatted_phone,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', message.from_user.id).execute()
        
        # Показываем что сохранили
        info_text = f"✅ *Телефон обновлён:*\n\n"
        info_text += f"📱 {formatted_phone}\n"
        if phone_info.get('valid'):
            info_text += f"🌍 {phone_info.get('country_name')} ({phone_info.get('country_code')})\n"
            info_text += f"📞 Тип: {phone_info.get('number_type')}"
        
        await message.answer(info_text, parse_mode="Markdown")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)
        
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при сохранении телефона")


@router.message(EditProfile.waiting_for_birthdate, F.text)
async def edit_birthdate(message: Message, state: FSMContext):
    """Обработка редактирования даты рождения"""
    date_string = message.text.strip()
    
    try:
        birthdate = parse_date(date_string)
        
        if birthdate > datetime.now():
            await message.answer("❌ Дата не может быть в будущем")
            return
        
        age = (datetime.now() - birthdate).days // 365
        
        if age < 1 or age > 120:
            await message.answer("❌ Укажите корректную дату")
            return
        
        supabase_client.table('user_profiles').update({
            'birthdate': birthdate.date().isoformat(),
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', message.from_user.id).execute()
        
        await message.answer(f"✅ Дата рождения обновлена: {birthdate.strftime('%d.%m.%Y')} ({age} лет)")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)
        
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте: ДД.ММ.ГГГГ")
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_gender, F.text.in_(["👨 Мужской", "👩 Женский"]))
async def edit_gender(message: Message, state: FSMContext):
    """Обработка редактирования пола"""
    gender = "male" if message.text == "👨 Мужской" else "female"
    
    try:
        supabase_client.table('user_profiles').update({
            'gender': gender,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', message.from_user.id).execute()
        
        await message.answer(f"✅ Пол обновлён: {message.text}", reply_markup=ReplyKeyboardRemove())
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)
        
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_height, F.text)
async def edit_height(message: Message, state: FSMContext):
    """Обработка редактирования роста"""
    try:
        height = int(message.text.strip())
        
        if height < 50 or height > 250:
            await message.answer("❌ Укажите корректный рост (50-250 см)")
            return
        
        supabase_client.table('user_profiles').update({
            'height': height,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', message.from_user.id).execute()
        
        await message.answer(f"✅ Рост обновлён: {height} см")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)
        
    except ValueError:
        await message.answer("❌ Введите число (например, 175)")
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_weight, F.text)
async def edit_weight(message: Message, state: FSMContext):
    """Обработка редактирования веса"""
    try:
        weight = float(message.text.strip().replace(",", "."))
        
        if weight < 20 or weight > 300:
            await message.answer("❌ Укажите корректный вес (20-300 кг)")
            return
        
        supabase_client.table('user_profiles').update({
            'weight': weight,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', message.from_user.id).execute()
        
        await message.answer(f"✅ Вес обновлён: {weight} кг")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)
        
    except ValueError:
        await message.answer("❌ Введите число (например, 70 или 70.5)")
    except Exception as e:
        print(f"DB Error: {e}")
        await message.answer("❌ Ошибка при сохранении")


# ============ ОТМЕНА ============

@router.message(F.text == "❌ Отменить")
async def cancel_profile_action(message: Message, state: FSMContext):
    """Отмена действия в профиле"""
    current_state = await state.get_state()
    
    # Если в процессе регистрации
    if current_state and current_state.startswith("Registration:"):
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена\n\n"
            "Для начала регистрации используйте /start",
            reply_markup=ReplyKeyboardRemove()
        )
    # Если в процессе редактирования
    elif current_state and current_state.startswith("EditProfile:"):
        await message.answer(
            "❌ Изменение отменено",
            reply_markup=get_edit_profile_menu()
        )
        await state.set_state(EditProfile.choosing_field)
    else:
        await state.clear()
        await message.answer(
            "Главное меню",
            reply_markup=get_main_menu()
        )
