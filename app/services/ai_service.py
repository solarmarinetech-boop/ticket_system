"""
AI Service — Groq API.

Регистрация (бесплатно, через Google или GitHub):
  https://console.groq.com → API Keys → Create API Key

Модель по умолчанию: llama-3.3-70b-versatile
Бесплатный лимит: 14 400 запросов/день, 500 000 токенов/мин — более чем достаточно для HelpDesk.
Groq совместим с форматом OpenAI, поэтому никакой дополнительной библиотеки не нужно — только openai SDK.
"""
import json
import logging
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

# Groq полностью совместим с OpenAI SDK — меняем только base_url и ключ
client = AsyncOpenAI(
    api_key=settings.groq_api_key,
    base_url="https://api.groq.com/openai/v1",
)

# Модели Groq (выбирается через ENV GROQ_MODEL):
#   llama-3.3-70b-versatile  — лучшее качество, рекомендуется
#   llama-3.1-8b-instant     — быстрее и дешевле, чуть слабее
#   mixtral-8x7b-32768       — хорошо понимает русский
SYSTEM_PROMPT = """Ты — умный ИТ-диспетчер компании. Твоя задача — помочь сотруднику правильно описать проблему и создать заявку.

ТВОИ ЗАДАЧИ:
1. Анализировать описание проблемы сотрудника.
2. Если информации НЕДОСТАТОЧНО — задать ОДИН уточняющий вопрос (самый важный).
3. Если информации ДОСТАТОЧНО — вернуть JSON с классификацией заявки.

СЦЕНАРИИ МАРШРУТИЗАЦИИ (scenario_key):
- "new_hire"      — подключение нового сотрудника (учётная запись, почта, ПО, оборудование)
- "hardware_fail" — поломка или выдача оборудования (мышь, клавиатура, монитор, ПК, ноутбук)
- "software"      — проблемы с программным обеспечением, установка ПО
- "access"        — доступ к системам, паролям, сетевым ресурсам
- "network"       — проблемы с интернетом, сетью, VPN
- "default"       — всё остальное

ОПРЕДЕЛЕНИЕ ПРИОРИТЕТА (priority):
- "critical" — сотрудник полностью не может работать / затронуто несколько человек
- "high"     — сотрудник сильно ограничен в работе
- "normal"   — работа возможна, но с неудобствами
- "low"      — косметическая проблема, несрочно

ФОРМАТ ОТВЕТА:
Если нужен уточняющий вопрос — отвечай ТОЛЬКО текстом вопроса (без JSON).
Если информации достаточно — отвечай ТОЛЬКО валидным JSON:
{
  "ready": true,
  "scenario_key": "hardware_fail",
  "priority": "normal",
  "title": "Не работает мышь",
  "entities": {
    "device": "мышь",
    "department": "Бухгалтерия"
  }
}

ПРАВИЛА:
- Максимум 2 уточняющих вопроса, потом в любом случае создавай заявку.
- Только ОДИН вопрос за раз, самый важный.
- Отвечай на русском языке, вежливо и кратко.
- Никаких markdown, преамбул или пояснений — только вопрос ИЛИ только JSON.
"""


async def process_ticket_interview(
    conversation_history: list[dict],
    clarification_count: int = 0,
) -> dict:
    """
    Ведёт AI-интервью для создания заявки.

    Args:
        conversation_history: история в формате [{"role": "user"|"assistant", "content": "..."}]
        clarification_count:  сколько уточняющих вопросов уже было задано

    Returns:
        {"ready": False, "question": "..."} — нужен ещё вопрос
        {"ready": True, "scenario_key": ..., "priority": ..., "title": ..., "entities": {...}}
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)

    # После 2 уточнений принудительно требуем создать заявку
    if clarification_count >= 2:
        messages.append({
            "role": "system",
            "content": (
                "Информации достаточно для создания заявки. "
                "Верни ТОЛЬКО JSON прямо сейчас, без вопросов."
            ),
        })

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            max_tokens=512,
            temperature=0.2,
        )
        text = response.choices[0].message.content.strip()

        # Убираем возможные markdown-тройные кавычки от модели
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()

        # Пробуем распарсить как JSON
        if text.startswith("{"):
            data = json.loads(text)
            if data.get("ready"):
                return {
                    "ready": True,
                    "scenario_key": data.get("scenario_key", "default"),
                    "priority": data.get("priority", "normal"),
                    "title": data.get("title", "Новая заявка"),
                    "entities": data.get("entities", {}),
                }

        # Это уточняющий вопрос
        return {"ready": False, "question": text}

    except json.JSONDecodeError:
        logger.warning(f"Groq вернул не-JSON при ready=true: {text!r}")
        # Считаем это вопросом, чтобы не сломать flow
        return {"ready": False, "question": text}
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return {
            "ready": False,
            "question": "Сервис временно недоступен. Опишите проблему подробнее — я создам заявку.",
        }


async def classify_ticket_text(text: str) -> dict:
    """Быстрая классификация без интервью (принудительно создаёт JSON)."""
    return await process_ticket_interview(
        [{"role": "user", "content": text}],
        clarification_count=2,
    )
