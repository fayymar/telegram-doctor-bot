from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states import FindSpecialist
from bot.keyboards import get_specialist_categories, get_specialists_in_category


router = Router()


# Данные о специалистах
SPECIALISTS_DATA = {
    "Кардиолог": {
        "description": "Специалист по заболеваниям сердца и сосудов",
        "symptoms": "боли в груди, одышка, нарушения ритма сердца, повышенное давление"
    },
    "Невролог": {
        "description": "Специалист по заболеваниям нервной системы",
        "symptoms": "головные боли, головокружения, онемение конечностей, судороги"
    },
    "Гастроэнтеролог": {
        "description": "Специалист по заболеваниям ЖКТ",
        "symptoms": "боли в животе, изжога, тошнота, проблемы со стулом"
    },
    "Эндокринолог": {
        "description": "Специалист по гормональным нарушениям",
        "symptoms": "нарушения веса, жажда, утомляемость, проблемы с щитовидкой"
    },
    "Пульмонолог": {
        "description": "Специалист по заболеваниям дыхательной системы",
        "symptoms": "кашель, одышка, хрипы, боли при дыхании"
    },
    "Уролог": {
        "description": "Специалист по заболеваниям мочеполовой системы (мужчины)",
        "symptoms": "боли при мочеиспускании, проблемы с почками, половые дисфункции"
    },
    "Гинеколог": {
        "description": "Специалист по женскому здоровью",
        "symptoms": "нарушения цикла, боли внизу живота, выделения"
    },
    "Дерматолог": {
        "description": "Специалист по заболеваниям кожи",
        "symptoms": "сыпь, зуд, пятна, проблемы с волосами и ногтями"
    },
    "Офтальмолог": {
        "description": "Специалист по заболеваниям глаз",
        "symptoms": "снижение зрения, боли в глазах, покраснение, слезотечение"
    },
    "Отоларинголог (ЛОР)": {
        "description": "Специалист по заболеваниям уха, горла и носа",
        "symptoms": "боль в горле, заложенность носа, боли в ушах, насморк"
    },
    "Ортопед-травматолог": {
        "description": "Специалист по заболеваниям костей и суставов",
        "symptoms": "боли в суставах, травмы, проблемы с позвоночником"
    },
    "Ревматолог": {
        "description": "Специалист по аутоиммунным заболеваниям суставов",
        "symptoms": "боли в суставах, скованность по утрам, отеки суставов"
    },
    "Аллерголог-иммунолог": {
        "description": "Специалист по аллергиям и иммунным нарушениям",
        "symptoms": "аллергические реакции, частые простуды, непереносимость продуктов"
    },
    "Психиатр": {
        "description": "Специалист по психическим расстройствам",
        "symptoms": "депрессия, тревога, нарушения сна, изменения настроения"
    },
    "Онколог": {
        "description": "Специалист по онкологическим заболеваниям",
        "symptoms": "новообразования, необъяснимая потеря веса, длительные симптомы"
    },
    "Хирург": {
        "description": "Специалист по хирургическим вмешательствам",
        "symptoms": "острые боли в животе, травмы, новообразования требующие операции"
    },
    "Проктолог": {
        "description": "Специалист по заболеваниям прямой кишки",
        "symptoms": "боли при дефекации, кровотечения, геморрой"
    },
    "Маммолог": {
        "description": "Специалист по заболеваниям молочных желез",
        "symptoms": "боли в груди, уплотнения, выделения из сосков"
    },
    "Нефролог": {
        "description": "Специалист по заболеваниям почек",
        "symptoms": "боли в пояснице, отеки, изменения в анализах мочи"
    },
    "Флеболог": {
        "description": "Специалист по заболеваниям вен",
        "symptoms": "варикоз, отеки ног, боли в венах"
    },
    "Сосудистый хирург": {
        "description": "Специалист по сосудистым заболеваниям",
        "symptoms": "боли в ногах при ходьбе, холодные конечности, язвы"
    },
    "Нейрохирург": {
        "description": "Специалист по хирургии нервной системы",
        "symptoms": "грыжи позвоночника, опухоли мозга, серьезные травмы"
    },
    "Гепатолог": {
        "description": "Специалист по заболеваниям печени",
        "symptoms": "желтуха, боли в правом подреберье, изменения в анализах"
    },
    "Диабетолог": {
        "description": "Специалист по диабету",
        "symptoms": "повышенный сахар, жажда, частое мочеиспускание"
    },
    "Фтизиатр": {
        "description": "Специалист по туберкулезу",
        "symptoms": "длительный кашель, ночная потливость, потеря веса"
    },
    "Мануальный терапевт": {
        "description": "Специалист по мануальной терапии позвоночника",
        "symptoms": "боли в спине, скованность, мышечные зажимы"
    },
    "Сурдолог": {
        "description": "Специалист по нарушениям слуха",
        "symptoms": "снижение слуха, шум в ушах, головокружения"
    },
    "Трихолог": {
        "description": "Специалист по заболеваниям волос и кожи головы",
        "symptoms": "выпадение волос, перхоть, зуд кожи головы"
    },
    "Андролог": {
        "description": "Специалист по мужскому здоровью",
        "symptoms": "половые дисфункции, бесплодие, гормональные нарушения"
    },
    "Инфекционист": {
        "description": "Специалист по инфекционным заболеваниям",
        "symptoms": "высокая температура, признаки инфекции, контакт с больными"
    },
    "Терапевт": {
        "description": "Врач общей практики",
        "symptoms": "любые жалобы на здоровье для первичного осмотра"
    }
}


# ============ ГЛАВНОЕ МЕНЮ СПЕЦИАЛИСТОВ ============

@router.message(F.text == "🔍 Найти специалиста")
async def show_specialist_categories(message: Message, state: FSMContext):
    """Показывает категории специалистов"""
    await state.clear()  # Сбрасываем предыдущие состояния
    
    await message.answer(
        "🔍 *Найти специалиста*\n\n"
        "Выберите категорию:",
        reply_markup=get_specialist_categories(),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.choosing_category)


# ============ ВЫБОР КАТЕГОРИИ ============

@router.callback_query(FindSpecialist.choosing_category, F.data.startswith("cat_"))
async def show_specialists_in_category(callback: CallbackQuery, state: FSMContext):
    """Показывает специалистов в выбранной категории"""
    category = callback.data.split("_")[1]
    
    category_names = {
        "cardio": "❤️ Сердце и сосуды",
        "neuro": "🧠 Нервная система",
        "gastro": "🍽 Пищеварение",
        "endo": "💊 Гормоны и обмен веществ",
        "pulmo": "🫁 Дыхательная система",
        "ortho": "🦴 Опорно-двигательный аппарат",
        "sense": "👁 Зрение и слух",
        "derm": "🧬 Кожа и аллергия",
        "repro": "👶 Женское и мужское здоровье",
        "other": "🩺 Другие специалисты"
    }
    
    await state.update_data(current_category=category)
    
    await callback.message.edit_text(
        f"*{category_names.get(category, 'Специалисты')}*\n\n"
        "Выберите специалиста для подробной информации:",
        reply_markup=get_specialists_in_category(category),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.viewing_specialists)
    await callback.answer()


# ============ ПРОСМОТР ИНФОРМАЦИИ О СПЕЦИАЛИСТЕ ============

@router.callback_query(FindSpecialist.viewing_specialists, F.data.startswith("spec_"))
async def show_specialist_info(callback: CallbackQuery, state: FSMContext):
    """Показывает информацию о специалисте"""
    specialist_name = callback.data.replace("spec_", "")
    
    specialist_info = SPECIALISTS_DATA.get(specialist_name, {
        "description": "Информация недоступна",
        "symptoms": "—"
    })
    
    info_text = f"🩺 *{specialist_name}*\n\n"
    info_text += f"📋 {specialist_info['description']}\n\n"
    info_text += f"🔍 *Основные симптомы:*\n{specialist_info['symptoms']}\n\n"
    info_text += "💡 *Как записаться:*\n"
    info_text += "Функция записи к врачу находится в разработке.\n"
    info_text += "Пока вы можете начать консультацию для получения рекомендации."
    
    # Кнопки действий
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🩺 Начать консультацию", callback_data="start_consultation_specialist")],
        [InlineKeyboardButton(text="🔙 К списку специалистов", callback_data="back_to_specialists")]
    ])
    
    await callback.message.edit_text(
        info_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "start_consultation_specialist")
async def start_consultation_from_specialist(callback: CallbackQuery, state: FSMContext):
    """Начинает консультацию из раздела специалистов"""
    from bot.handlers.consultation import start_consultation
    
    await callback.message.delete()
    await state.clear()
    
    # Имитируем сообщение для запуска консультации
    fake_message = callback.message
    fake_message.text = "🩺 Новая консультация"
    
    await start_consultation(fake_message, state)
    await callback.answer()


# ============ НАВИГАЦИЯ ============

@router.callback_query(F.data == "back_to_specialists")
async def back_to_specialists_list(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку специалистов в категории"""
    data = await state.get_data()
    category = data.get('current_category', 'cardio')
    
    category_names = {
        "cardio": "❤️ Сердце и сосуды",
        "neuro": "🧠 Нервная система",
        "gastro": "🍽 Пищеварение",
        "endo": "💊 Гормоны и обмен веществ",
        "pulmo": "🫁 Дыхательная система",
        "ortho": "🦴 Опорно-двигательный аппарат",
        "sense": "👁 Зрение и слух",
        "derm": "🧬 Кожа и аллергия",
        "repro": "👶 Женское и мужское здоровье",
        "other": "🩺 Другие специалисты"
    }
    
    await callback.message.edit_text(
        f"*{category_names.get(category, 'Специалисты')}*\n\n"
        "Выберите специалиста для подробной информации:",
        reply_markup=get_specialists_in_category(category),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.viewing_specialists)
    await callback.answer()


@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    """Возврат к категориям специалистов"""
    await callback.message.edit_text(
        "🔍 *Найти специалиста*\n\n"
        "Выберите категорию:",
        reply_markup=get_specialist_categories(),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.choosing_category)
    await callback.answer()
