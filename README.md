# HelpDesk IT — Telegram Bot + Web Console

Система управления ИТ-заявками на базе Telegram Bot + FastAPI Web Console с AI-маршрутизацией.

## Стек

- **Backend**: Python 3.12 + FastAPI
- **Bot**: Aiogram 3.x (async)
- **Database**: PostgreSQL (Railway)
- **AI**: OpenAI API (GPT-4o) — настраивается через ENV
- **Frontend**: Jinja2 + Vanilla JS (внутри FastAPI)
- **Deploy**: Railway + Docker + GitHub Actions

## Структура проекта

```
helpdesk/
├── app/
│   ├── bot/
│   │   ├── handlers/          # Обработчики команд бота
│   │   │   ├── common.py      # /start, регистрация
│   │   │   ├── user.py        # Создание заявок (AI-interview)
│   │   │   ├── executor.py    # Работа исполнителя
│   │   │   └── admin.py       # Команды администратора
│   │   ├── keyboards/
│   │   │   └── inline.py      # Inline-клавиатуры
│   │   └── middlewares/
│   │       └── role.py        # RBAC middleware
│   ├── api/
│   │   └── routers/
│   │       ├── auth.py        # Авторизация веб-консоли
│   │       ├── tickets.py     # CRUD заявок
│   │       ├── users.py       # Управление пользователями
│   │       └── routes.py      # Настройка маршрутов
│   ├── db/
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── ticket.py
│   │   │   └── route.py
│   │   ├── base.py
│   │   └── session.py
│   ├── services/
│   │   ├── ai_service.py      # LLM интеграция (классификация + интервью)
│   │   ├── routing_service.py # Логика маршрутизации
│   │   └── notification.py    # Уведомления через бот
│   ├── templates/admin/       # Jinja2 шаблоны веб-консоли
│   ├── static/                # CSS, JS
│   ├── config.py              # Настройки из ENV
│   └── main.py                # Точка входа (FastAPI + Aiogram)
├── migrations/                # Alembic миграции
├── tests/
├── Dockerfile
├── docker-compose.yml         # Для локальной разработки
├── .github/workflows/
│   └── deploy.yml             # CI/CD на Railway
├── requirements.txt
└── .env.example
```

## Быстрый старт (локально)

```bash
# 1. Скопировать переменные окружения
cp .env.example .env
# Заполнить .env своими значениями

# 2. Запустить через Docker Compose
docker-compose up --build

# 3. Применить миграции
docker-compose exec app alembic upgrade head
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram бота (BotFather) |
| `DATABASE_URL` | PostgreSQL connection string |
| `OPENAI_API_KEY` | Ключ OpenAI API |
| `OPENAI_MODEL` | Модель (по умолчанию: gpt-4o) |
| `SECRET_KEY` | JWT секрет для веб-консоли |
| `ADMIN_CHAT_IDS` | Telegram ID администраторов (через запятую) |
| `WEBHOOK_URL` | URL для Telegram webhook (Railway URL) |
| `WEBHOOK_PATH` | Путь webhook (по умолчанию: /webhook) |

## Ролевая модель

- **Пользователь** — создаёт заявки, видит статус своих заявок
- **Исполнитель** — получает задачи, меняет статусы, добавляет комментарии
- **Администратор** — полный доступ + веб-консоль

## Сценарии маршрутизации (по умолчанию)

| Тип заявки | Цепочка исполнителей |
|---|---|
| `new_hire` | Юра → Стас → Андрей |
| `hardware_fail` | Андрей |
| `software` | Стас |
| `access` | Юра |
| `default` | Дежурный / Администратор |

## Deploy на Railway

1. Push в ветку `main`
2. GitHub Actions автоматически деплоит на Railway
3. Railway читает `Dockerfile` и переменные окружения из панели Railway
