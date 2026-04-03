import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HF_API_URL = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
HF_TOKEN = os.getenv("HF_TOKEN", "")


def get_embedding(text: str) -> list:
    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    response = httpx.post(
        HF_API_URL,
        headers=headers,
        json={"inputs": text},
        timeout=30.0
    )
    if response.status_code == 200:
        result = response.json()
        if isinstance(result, list) and isinstance(result[0], list):
            return result[0]
        return result
    return []


with open("services/data/icd10_mapping.json", "r", encoding="utf-8") as f:
    icd10_data = json.load(f)

print(f"Загружаем {len(icd10_data)} болезней...")

batch = []
for code, data in icd10_data.items():
    disease_name = data.get("name", "") or data.get("description", "") or str(data)
    symptoms = data.get("symptoms", "") or data.get("keywords", "") or ""
    specialist = data.get("specialist", "") or data.get("category", "")

    if isinstance(symptoms, list):
        symptoms = ", ".join(symptoms)
    if isinstance(specialist, list):
        specialist = ", ".join(specialist)

    text_to_embed = f"{disease_name}. Симптомы: {symptoms}"

    batch.append({
        "code": code,
        "disease_name": disease_name,
        "symptoms": symptoms,
        "specialist": specialist,
        "text": text_to_embed
    })

texts = [item["text"] for item in batch]
print("Генерируем эмбеддинги...")

embeddings = []
for i, text in enumerate(texts):
    emb = get_embedding(text)
    embeddings.append(emb)
    if (i + 1) % 100 == 0:
        print(f"Эмбеддинги: {i + 1}/{len(texts)}")

print("Загружаем в Supabase...")
for i, (item, embedding) in enumerate(zip(batch, embeddings)):
    supabase.table("medical_embeddings").insert({
        "code": item["code"],
        "disease_name": item["disease_name"],
        "symptoms": item["symptoms"],
        "specialist": item["specialist"],
        "embedding": embedding
    }).execute()

    if (i + 1) % 100 == 0:
        print(f"Загружено {i + 1}/{len(batch)}")

print("Готово!")
