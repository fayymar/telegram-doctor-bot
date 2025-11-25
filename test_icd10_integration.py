"""
Тест интеграции МКБ-10
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.medical_knowledge import LocalMedicalDB

def test_icd10():
    """Тест МКБ-10 интеграции"""
    db = LocalMedicalDB()

    print("=" * 70)
    print("ТЕСТ ИНТЕГРАЦИИ МКБ-10")
    print("=" * 70)

    # Тест 1: Головная боль
    print("\n📋 ТЕСТ 1: Головная боль")
    print("-" * 70)
    result = db.search("Болит голова уже два дня")
    if result:
        print(f"✅ Найдено: {result['matched_keyword']}")
        print(f"   МКБ-10: {result['icd10_code']} - {result['icd10_name']}")
        print(f"   Уверенность: {result['confidence']:.0%}")
        print(f"   Специалисты:")
        for spec in result['specialists']:
            print(f"      • {spec['name']} - {spec['percent']}%")
    else:
        print("❌ Не найдено")

    # Тест 2: Боль в животе
    print("\n📋 ТЕСТ 2: Боль в животе")
    print("-" * 70)
    result = db.search("Боль в животе справа внизу")
    if result:
        print(f"✅ Найдено: {result['matched_keyword']}")
        print(f"   МКБ-10: {result['icd10_code']} - {result['icd10_name']}")
        print(f"   Уверенность: {result['confidence']:.0%}")
        print(f"   Красные флаги: {'Да' if result['red_flags_found'] else 'Нет'}")
        print(f"   Специалисты:")
        for spec in result['specialists']:
            print(f"      • {spec['name']} - {spec['percent']}%")
    else:
        print("❌ Не найдено")

    # Тест 3: Боль в сердце
    print("\n📋 ТЕСТ 3: Боль в сердце (должна быть высокая уверенность)")
    print("-" * 70)
    result = db.search("Болит сердце давящая боль")
    if result:
        print(f"✅ Найдено: {result['matched_keyword']}")
        print(f"   МКБ-10: {result['icd10_code']} - {result['icd10_name']}")
        print(f"   Уверенность: {result['confidence']:.0%}")
        print(f"   Специалисты:")
        for spec in result['specialists']:
            print(f"      • {spec['name']} - {spec['percent']}%")
    else:
        print("❌ Не найдено")

    # Тест 4: Кашель
    print("\n📋 ТЕСТ 4: Кашель")
    print("-" * 70)
    result = db.search("Сухой кашель более недели")
    if result:
        print(f"✅ Найдено: {result['matched_keyword']}")
        print(f"   МКБ-10: {result['icd10_code']} - {result['icd10_name']}")
        print(f"   Уверенность: {result['confidence']:.0%}")
        print(f"   Специалисты:")
        for spec in result['specialists']:
            print(f"      • {spec['name']} - {spec['percent']}%")
    else:
        print("❌ Не найдено")

    # Статистика
    print("\n" + "=" * 70)
    print("📊 СТАТИСТИКА")
    print("-" * 70)
    print(f"Симптомов в базе: {len(db.symptoms_db)}")
    print(f"Кодов МКБ-10: {len(db.icd10_mapping.get('specific_codes', {}))}")
    print(f"Категорий МКБ-10: {len(db.icd10_mapping.get('categories', {}))}")

    print("\n✅ Тесты завершены!")
    print("=" * 70)

if __name__ == "__main__":
    test_icd10()
