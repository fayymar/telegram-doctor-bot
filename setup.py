#!/usr/bin/env python3
"""
Скрипт для первоначальной настройки проекта
"""
import os
def create_directories():
    """Создать необходимые директории"""
    directories = [
        "bot/handlers",
        "database",
        "services",
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✓ Создана директория: {directory}")


def create_init_files():
    """Создать __init__.py файлы"""
    init_files = [
        "bot/__init__.py",
        "bot/handlers/__init__.py",
        "database/__init__.py",
        "services/__init__.py",
    ]
    
    for init_file in init_files:
        if not os.path.exists(init_file):
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write('"""Package initialization"""\n')
            print(f"✓ Создан файл: {init_file}")


def check_env_file():
    """Проверить наличие .env файла"""
    if not os.path.exists('.env'):
        print("\n⚠️  Файл .env не найден!")
        print("Создайте файл .env на основе .env.example:")
        print("  cp .env.example .env")
        print("\nЗатем заполните все переменные окружения.")
        return False
    print("✓ Файл .env найден")
    return True


def main():
    """Главная функция"""
    print("🚀 Настройка проекта telegram-doctor-bot\n")
    
    print("1. Создание директорий...")
    create_directories()
    
    print("\n2. Создание __init__.py файлов...")
    create_init_files()
    
    print("\n3. Проверка переменных окружения...")
    env_exists = check_env_file()
    
    print("\n" + "="*50)
    print("✅ Структура проекта готова!")
    print("="*50)
    
    if not env_exists:
        print("\n📋 Следующие шаги:")
        print("1. Создайте .env файл: cp .env.example .env")
        print("2. Заполните переменные окружения в .env")
        print("3. Создайте таблицы в Supabase (используйте supabase_schema.sql)")
        print("4. Установите зависимости: pip install -r requirements.txt")
        print("5. Запустите бота: python main.py")
    else:
        print("\n📋 Следующие шаги:")
        print("1. Проверьте переменные окружения в .env")
        print("2. Создайте таблицы в Supabase (используйте supabase_schema.sql)")
        print("3. Установите зависимости: pip install -r requirements.txt")
        print("4. Запустите бота: python main.py")


if __name__ == "__main__":
    main()
