"""
Тест гибридной системы рекомендаций
"""
import sys
import os

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Загружаем .env если возможно
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv не обязателен для теста

from services.medical_router import MedicalRouter

def test_hybrid_system():
    """Тест гибридной системы"""
    router = MedicalRouter()

    print("=" * 60)
    print("ТЕСТ ГИБРИДНОЙ СИСТЕМЫ РЕКОМЕНДАЦИЙ")
    print("=" * 60)

    # Тест 1: Простой случай (должен использовать локальную БД)
    print("\n📋 ТЕСТ 1: Головная боль (простой случай)")
    print("-" * 60)
    result = router.recommend_doctor(
        main_symptoms="Болит голова уже два дня",
        duration="2 дня",
        additional_symptoms=[],
        user_profile={'age': 30, 'gender': 'male'}
    )
    print(f"Источник: {result.get('source', 'unknown')}")
    print(f"Уверенность: {result.get('confidence', 'N/A')}")
    print(f"Срочность: {result['urgency']}")
    print(f"Специалисты:")
    for spec in result['specialists'][:3]:
        print(f"  • {spec['name']} - {spec['match_percent']}%")
        print(f"    {spec['reason']}")

    # Тест 2: Случай с красными флагами (должен использовать AI)
    print("\n📋 ТЕСТ 2: Головная боль с красными флагами")
    print("-" * 60)
    result = router.recommend_doctor(
        main_symptoms="Острая резкая головная боль с тошнотой и рвотой",
        duration="Несколько часов",
        additional_symptoms=["Нарушение зрения"],
        user_profile={'age': 45, 'gender': 'female'}
    )
    print(f"Источник: {result.get('source', 'unknown')}")
    print(f"Уверенность: {result.get('confidence', 'N/A')}")
    print(f"Срочность: {result['urgency']}")
    print(f"Специалисты:")
    for spec in result['specialists'][:3]:
        print(f"  • {spec['name']} - {spec['match_percent']}%")
        print(f"    {spec['reason'][:80]}...")

    # Тест 3: Сложный случай (должен использовать AI)
    print("\n📋 ТЕСТ 3: Сложные симптомы (должен использовать AI)")
    print("-" * 60)
    result = router.recommend_doctor(
        main_symptoms="Постоянная усталость, головокружение, учащенное сердцебиение",
        duration="Несколько недель",
        additional_symptoms=["Одышка при нагрузке", "Бледность"],
        user_profile={'age': 35, 'gender': 'female'}
    )
    print(f"Источник: {result.get('source', 'unknown')}")
    print(f"Уверенность: {result.get('confidence', 'N/A')}")
    print(f"Срочность: {result['urgency']}")
    print(f"Специалисты:")
    for spec in result['specialists'][:3]:
        print(f"  • {spec['name']} - {spec['match_percent']}%")
        print(f"    {spec['reason'][:80]}...")

    # Статистика
    print("\n📊 СТАТИСТИКА СИСТЕМЫ")
    print("-" * 60)
    stats = router.get_stats()
    print(f"Симптомов в локальной БД: {stats['local_db_symptoms']}")
    print(f"Порог уверенности: {stats['confidence_threshold'] * 100}%")

    print("\n✅ Тесты завершены!")
    print("=" * 60)

if __name__ == "__main__":
    test_hybrid_system()
