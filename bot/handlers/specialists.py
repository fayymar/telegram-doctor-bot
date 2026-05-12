from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.states import FindSpecialist
from bot.keyboards import get_specialist_categories, get_specialists_in_category, get_specialist_actions, get_main_menu


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


# Карта категорий
CATEGORY_SPECIALISTS = {
    "❤️ Сердце и сосуды": ["Кардиолог", "Флеболог", "Сосудистый хирург"],
    "🧠 Нервная система": ["Невролог", "Нейрохирург", "Психиатр"],
    "🍽 Пищеварение": ["Гастроэнтеролог", "Проктолог", "Гепатолог"],
    "💊 Гормоны и обмен веществ": ["Эндокринолог", "Диабетолог"],
    "🫁 Дыхательная система": ["Пульмонолог", "Фтизиатр"],
    "🦴 Опорно-двигательный аппарат": ["Ортопед-травматолог", "Ревматолог", "Мануальный терапевт"],
    "👁 Зрение и слух": ["Офтальмолог", "Отоларинголог (ЛОР)", "Сурдолог"],
    "🧬 Кожа и аллергия": ["Дерматолог", "Аллерголог-иммунолог", "Трихолог"],
    "👶 Женское и мужское здоровье": ["Гинеколог", "Уролог", "Маммолог", "Андролог"],
    "🩺 Другие специалисты": ["Хирург", "Онколог", "Нефролог", "Инфекционист", "Терапевт"]
}


# ============ ГЛАВНОЕ МЕНЮ СПЕЦИАЛИСТОВ ============

@router.message(F.text.in_({"🔍 Найти специалиста", "👨‍⚕️ Найти специалиста"}))
async def show_specialist_categories(message: Message, state: FSMContext):
    """Показывает категории специалистов"""
    await state.clear()
    
    await message.answer(
        "🔍 *Найти специалиста*\n\n"
        "Выберите категорию:",
        reply_markup=get_specialist_categories(),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.choosing_category)


# ============ ВЫБОР КАТЕГОРИИ ============

@router.message(FindSpecialist.choosing_category, F.text.in_(CATEGORY_SPECIALISTS.keys()))
async def show_specialists_in_category(message: Message, state: FSMContext):
    """Показывает специалистов в выбранной категории"""
    category = message.text
    specialists = CATEGORY_SPECIALISTS[category]
    
    await state.update_data(current_category=category)
    
    await message.answer(
        f"*{category}*\n\n"
        "Выберите специалиста для подробной информации:",
        reply_markup=get_specialists_in_category(specialists),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.viewing_specialists)


# ============ ПРОСМОТР ИНФОРМАЦИИ О СПЕЦИАЛИСТЕ ============

@router.message(FindSpecialist.viewing_specialists, F.text.startswith("🩺 "))
async def show_specialist_info(message: Message, state: FSMContext):
    """Показывает информацию о специалисте"""
    specialist_name = message.text.replace("🩺 ", "")
    
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
    
    await message.answer(
        info_text,
        reply_markup=get_specialist_actions(),
        parse_mode="Markdown"
    )


@router.message(F.text == "🩺 Начать консультацию")
async def start_consultation_from_specialist(message: Message, state: FSMContext):
    """Начинает консультацию из раздела специалистов"""
    from bot.handlers.consultation import start_consultation
    
    await state.clear()
    await start_consultation(message, state)


# ============ НАВИГАЦИЯ ============

@router.message(F.text == "🔙 К списку специалистов")
async def back_to_specialists_list(message: Message, state: FSMContext):
    """Возврат к списку специалистов в категории"""
    data = await state.get_data()
    category = data.get('current_category', '❤️ Сердце и сосуды')
    
    specialists = CATEGORY_SPECIALISTS[category]
    
    await message.answer(
        f"*{category}*\n\n"
        "Выберите специалиста для подробной информации:",
        reply_markup=get_specialists_in_category(specialists),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.viewing_specialists)


@router.message(F.text == "🔙 К категориям")
async def back_to_categories(message: Message, state: FSMContext):
    """Возврат к категориям специалистов"""
    await message.answer(
        "🔍 *Найти специалиста*\n\n"
        "Выберите категорию:",
        reply_markup=get_specialist_categories(),
        parse_mode="Markdown"
    )
    await state.set_state(FindSpecialist.choosing_category)
