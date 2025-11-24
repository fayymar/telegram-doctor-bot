"""Модуль локализации (i18n) для поддержки нескольких языков"""

# Словарь переводов
TRANSLATIONS = {
    # Общие
    "cancel": {
        "ru": "❌ Отменить",
        "uz": "❌ Bekor qilish"
    },
    "back": {
        "ru": "🔙 Назад",
        "uz": "🔙 Orqaga"
    },
    "skip": {
        "ru": "⏭ Пропустить",
        "uz": "⏭ O'tkazib yuborish"
    },
    "confirm": {
        "ru": "✅ Подтвердить",
        "uz": "✅ Tasdiqlash"
    },
    "save": {
        "ru": "✅ Сохранить",
        "uz": "✅ Saqlash"
    },

    # Главное меню
    "menu_consultation": {
        "ru": "🩺 Новая консультация",
        "uz": "🩺 Yangi konsultatsiya"
    },
    "menu_profile": {
        "ru": "👤 Профиль",
        "uz": "👤 Profil"
    },
    "menu_history": {
        "ru": "📋 История",
        "uz": "📋 Tarix"
    },
    "menu_medications": {
        "ru": "💊 Лекарства",
        "uz": "💊 Dorilar"
    },
    "menu_diary": {
        "ru": "📓 Дневник",
        "uz": "📓 Kundalik"
    },
    "menu_find_clinics": {
        "ru": "🗺 Найти клиники",
        "uz": "🗺 Klinikalarni topish"
    },
    "menu_find_specialist": {
        "ru": "🔍 Найти специалиста",
        "uz": "🔍 Mutaxassisni topish"
    },
    "menu_export": {
        "ru": "💾 Экспорт анамнеза",
        "uz": "💾 Anamnezni eksport qilish"
    },
    "menu_help": {
        "ru": "ℹ️ Помощь",
        "uz": "ℹ️ Yordam"
    },
    "menu_main": {
        "ru": "🔙 В главное меню",
        "uz": "🔙 Asosiy menyuga"
    },

    # Приветствие
    "welcome_new": {
        "ru": (
            "👋 Добро пожаловать!\n\n"
            "🩺 *Telegram Medical Bot*\n\n"
            "Я помогу вам:\n"
            "• Определить нужного специалиста\n"
            "• Оценить срочность обращения\n"
            "• Записаться на приём\n\n"
            "Для начала давайте заполним ваш профиль."
        ),
        "uz": (
            "👋 Xush kelibsiz!\n\n"
            "🩺 *Telegram Tibbiy Bot*\n\n"
            "Men sizga yordam beraman:\n"
            "• Kerakli mutaxassisni aniqlash\n"
            "• Murojaat shoshilinchligini baholash\n"
            "• Qabulga yozilish\n\n"
            "Avval profilingizni to'ldiraylik."
        )
    },
    "welcome_back": {
        "ru": "👋 С возвращением!\n\nВыберите действие:",
        "uz": "👋 Qaytganingiz bilan!\n\nAmalni tanlang:"
    },

    # Регистрация
    "registration_name": {
        "ru": "👤 *Как вас зовут?*\nВведите ФИО (например: Иванов Иван или Иван Петров)",
        "uz": "👤 *Ismingiz nima?*\nTo'liq ism-familiyangizni kiriting (masalan: Ivanov Ivan)"
    },
    "registration_phone": {
        "ru": (
            "📱 *Шаг 2 из 6*\n\n"
            "Поделитесь номером телефона\n\n"
            "Вы можете:\n"
            "• Нажать кнопку ниже\n"
            "• Ввести номер вручную (в любом формате)\n\n"
            "Примеры:\n"
            "• +998 90 123 45 67\n"
            "• 998901234567\n"
            "• 90 123 45 67"
        ),
        "uz": (
            "📱 *2-qadam 6 dan*\n\n"
            "Telefon raqamingizni ulashing\n\n"
            "Siz quyidagilarni amalga oshirishingiz mumkin:\n"
            "• Pastdagi tugmani bosing\n"
            "• Raqamni qo'lda kiriting (har qanday formatda)\n\n"
            "Misollar:\n"
            "• +998 90 123 45 67\n"
            "• 998901234567\n"
            "• 90 123 45 67"
        )
    },
    "registration_birthdate": {
        "ru": (
            "🎂 *Шаг 3 из 6*\n\n"
            "Введите дату рождения\n\n"
            "Формат: ДД.ММ.ГГГГ (например, 15.03.1990)\n"
            "Также принимается: 15/03/1990 или 15 03 1990"
        ),
        "uz": (
            "🎂 *3-qadam 6 dan*\n\n"
            "Tug'ilgan sanangizni kiriting\n\n"
            "Format: KK.OO.YYYY (masalan, 15.03.1990)\n"
            "Shuningdek qabul qilinadi: 15/03/1990 yoki 15 03 1990"
        )
    },
    "registration_gender": {
        "ru": "⚧️ *Шаг 4 из 6*\n\nВыберите пол:",
        "uz": "⚧️ *4-qadam 6 dan*\n\nJinsingizni tanlang:"
    },
    "registration_height": {
        "ru": "📏 *Шаг 5 из 6*\n\nВведите ваш рост в сантиметрах\nНапример: 175",
        "uz": "📏 *5-qadam 6 dan*\n\nBo'yingizni santimetrlarda kiriting\nMasalan: 175"
    },
    "registration_weight": {
        "ru": "⚖️ *Шаг 6 из 6*\n\nВведите ваш вес в килограммах\nНапример: 70 или 70.5",
        "uz": "⚖️ *6-qadam 6 dan*\n\nVazningizni kilogrammlarda kiriting\nMasalan: 70 yoki 70.5"
    },
    "registration_complete": {
        "ru": (
            "🎉 *Регистрация завершена!*\n\n"
            "Ваш профиль успешно создан.\n"
            "Теперь вы можете пользоваться всеми функциями бота!"
        ),
        "uz": (
            "🎉 *Ro'yxatdan o'tish yakunlandi!*\n\n"
            "Profilingiz muvaffaqiyatli yaratildi.\n"
            "Endi siz botning barcha funksiyalaridan foydalanishingiz mumkin!"
        )
    },

    # Пол
    "gender_male": {
        "ru": "👨 Мужской",
        "uz": "👨 Erkak"
    },
    "gender_female": {
        "ru": "👩 Женский",
        "uz": "👩 Ayol"
    },

    # Ошибки валидации
    "error_name_short": {
        "ru": "❌ ФИО слишком короткое (минимум 3 символа)",
        "uz": "❌ Ism juda qisqa (kamida 3 ta belgi)"
    },
    "error_name_format": {
        "ru": "❌ Пожалуйста, укажите хотя бы Фамилию и Имя\nНапример: Иванов Иван",
        "uz": "❌ Iltimos, kamida familiya va ismingizni kiriting\nMasalan: Ivanov Ivan"
    },
    "error_date_future": {
        "ru": "❌ Дата рождения не может быть в будущем",
        "uz": "❌ Tug'ilgan sana kelajakda bo'lishi mumkin emas"
    },
    "error_age_min": {
        "ru": "❌ Минимальный возраст для регистрации: 14 лет",
        "uz": "❌ Ro'yxatdan o'tish uchun minimal yosh: 14 yosh"
    },
    "error_db": {
        "ru": "❌ Произошла ошибка при подключении к базе данных.\nПопробуйте позже или обратитесь к администратору.",
        "uz": "❌ Ma'lumotlar bazasiga ulanishda xatolik yuz berdi.\nKeyinroq urinib ko'ring yoki administratorga murojaat qiling."
    },

    # Общие сообщения
    "main_menu": {
        "ru": "Главное меню",
        "uz": "Asosiy menyu"
    },
    "choose_action": {
        "ru": "Выберите действие:",
        "uz": "Amalni tanlang:"
    },
}


def get_text(key: str, lang: str = "ru") -> str:
    """
    Получить переведенный текст по ключу

    Args:
        key: Ключ перевода
        lang: Код языка (ru, uz)

    Returns:
        Переведенный текст
    """
    if key not in TRANSLATIONS:
        return f"[Missing translation: {key}]"

    translation = TRANSLATIONS[key]

    if lang not in translation:
        # Возвращаем русский по умолчанию
        return translation.get("ru", f"[Missing language: {lang}]")

    return translation[lang]


def t(key: str, lang: str = "ru") -> str:
    """Короткий алиас для get_text"""
    return get_text(key, lang)
