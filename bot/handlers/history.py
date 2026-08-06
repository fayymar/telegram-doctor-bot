"""Обработчики для истории консультаций"""
import json
import os
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.states import ViewHistory
from bot.keyboards import get_main_menu
from database.connection import supabase_client, run_query
from utils.logger import setup_logger
from utils.export_anamnesis import format_anamnesis_text, generate_filename

logger = setup_logger(__name__)
router = Router()


@router.message(F.text == "📋 История")
async def show_history(message: Message, state: FSMContext):
    """Показать историю консультаций"""
    try:
        # Получаем консультации пользователя
        response = await run_query(lambda: supabase_client.table('consultations')
            .select('*')
            .eq('user_id', message.from_user.id)
            .order('created_at', desc=True)
            .limit(10)
            .execute())

        if not response.data or len(response.data) == 0:
            await message.answer(
                "📋 *История консультаций*\n\n"
                "У вас пока нет консультаций.\n\n"
                "Создайте первую консультацию, нажав 🩺 *Новая консультация*",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
            return

        # Сохраняем консультации в state
        await state.update_data(consultations=response.data)

        # Формируем список консультаций
        history_text = "📋 *История консультаций*\n\n"
        history_text += f"Всего: {len(response.data)}\n\n"

        for idx, consultation in enumerate(response.data[:10], 1):
            # Парсим дату
            created = datetime.fromisoformat(consultation['created_at'].replace('Z', '+00:00'))
            date_str = created.strftime('%d.%m.%Y %H:%M')

            # Парсим симптомы
            try:
                symptoms_data = json.loads(consultation['symptoms'])
                main_symptom = symptoms_data.get('main', 'не указано')
                # Берем только первые 50 символов
                main_symptom_short = main_symptom[:50] + '...' if len(main_symptom) > 50 else main_symptom
            except:
                main_symptom_short = 'не указано'

            specialist = consultation['recommended_doctor']
            urgency = consultation['urgency_level']

            # Эмодзи для срочности
            urgency_emoji = {
                'low': 'ℹ️',
                'medium': '📋',
                'high': '⚠️',
                'emergency': '🚨'
            }.get(urgency, '📋')

            history_text += f"*{idx}.* {date_str}\n"
            history_text += f"   {urgency_emoji} {specialist}\n"
            history_text += f"   💬 {main_symptom_short}\n\n"

        history_text += "\n💡 Для просмотра деталей напишите номер (1-10)"

        await message.answer(
            history_text,
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )

        await state.set_state(ViewHistory.viewing_list)

    except Exception as e:
        logger.error(f"Error in show_history: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при загрузке истории консультаций",
            reply_markup=get_main_menu()
        )


@router.message(ViewHistory.viewing_list, F.text.regexp(r'^\d+$'))
async def show_consultation_details(message: Message, state: FSMContext):
    """Показать детали консультации по номеру"""
    try:
        consultation_num = int(message.text)

        # Получаем сохраненные консультации
        data = await state.get_data()
        consultations = data.get('consultations', [])

        if consultation_num < 1 or consultation_num > len(consultations):
            await message.answer(
                f"❌ Консультация №{consultation_num} не найдена\n\n"
                f"Доступные номера: 1-{len(consultations)}"
            )
            return

        consultation = consultations[consultation_num - 1]

        # Парсим данные
        created = datetime.fromisoformat(consultation['created_at'].replace('Z', '+00:00'))
        date_str = created.strftime('%d.%m.%Y в %H:%M')

        try:
            symptoms_data = json.loads(consultation['symptoms'])
            main_symptoms = symptoms_data.get('main', 'не указано')
            duration = symptoms_data.get('duration', 'не указано')
            additional = symptoms_data.get('additional', [])
        except:
            main_symptoms = 'не указано'
            duration = 'не указано'
            additional = []

        specialist = consultation['recommended_doctor']
        urgency = consultation['urgency_level']

        # Эмодзи для срочности
        urgency_emoji = {
            'low': 'ℹ️',
            'medium': '📋',
            'high': '⚠️',
            'emergency': '🚨'
        }.get(urgency, '📋')

        urgency_text = {
            'low': 'Низкая (плановый приём)',
            'medium': 'Средняя (в течение недели)',
            'high': 'Высокая (в течение 24 часов)',
            'emergency': 'СРОЧНО! Требуется скорая помощь'
        }.get(urgency, 'Не указано')

        # Формируем детальное описание
        details = f"📋 *Консультация №{consultation_num}*\n\n"
        details += f"📅 *Дата:* {date_str}\n"
        details += f"🩺 *Специалист:* {specialist}\n"
        details += f"{urgency_emoji} *Срочность:* {urgency_text}\n\n"

        details += f"*Основные симптомы:*\n{main_symptoms}\n\n"
        details += f"*Давность:* {duration}\n\n"

        if additional:
            details += "*Дополнительные симптомы:*\n"
            for symptom in additional:
                details += f"• {symptom}\n"
        else:
            details += "*Дополнительные симптомы:* нет\n"

        await message.answer(
            details,
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )

        # Выходим из состояния просмотра
        await state.clear()

    except Exception as e:
        logger.error(f"Error in show_consultation_details: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при загрузке деталей консультации",
            reply_markup=get_main_menu()
        )


@router.message(F.text == "💾 Экспорт анамнеза")
async def export_anamnesis(message: Message):
    """Экспортировать полный анамнез в текстовый файл"""
    try:
        user_id = message.from_user.id

        # Получаем профиль пользователя
        profile_response = await run_query(lambda: supabase_client.table('user_profiles')
            .select('*')
            .eq('user_id', user_id)
            .execute())

        if not profile_response.data or len(profile_response.data) == 0:
            await message.answer(
                "❌ Профиль не найден. Пожалуйста, зарегистрируйтесь сначала.",
                reply_markup=get_main_menu()
            )
            return

        user_profile = profile_response.data[0]

        # Получаем все консультации пользователя
        consultations_response = await run_query(lambda: supabase_client.table('consultations')
            .select('*')
            .eq('user_id', user_id)
            .order('created_at', desc=True)
            .execute())

        consultations = consultations_response.data if consultations_response.data else []

        # Генерируем текст анамнеза
        anamnesis_text = format_anamnesis_text(user_profile, consultations)

        # Создаем временный файл
        filename = generate_filename(user_id, user_profile.get('full_name'))
        temp_path = f"/tmp/{filename}"

        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(anamnesis_text)

        # Отправляем файл пользователю
        document = FSInputFile(temp_path, filename=filename)

        caption = (
            "📄 *Ваш медицинский анамнез*\n\n"
            f"Профиль: {user_profile.get('full_name', 'Не указано')}\n"
            f"Консультаций: {len(consultations)}\n\n"
            "⚠️ Этот документ носит информационный характер"
        )

        await message.answer_document(
            document=document,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )

        # Удаляем временный файл
        try:
            os.remove(temp_path)
        except:
            pass

        logger.info(f"Anamnesis exported for user {user_id}")

    except Exception as e:
        logger.error(f"Error in export_anamnesis: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при экспорте анамнеза. Попробуйте позже.",
            reply_markup=get_main_menu()
        )
