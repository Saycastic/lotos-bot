# LotOS Bot

Telegram-бот для приёма заявок на разработку ботов, сайтов и настройку серверов.

## Стек
- Python 3.11+
- python-telegram-bot 22.x
- SQLite

## Структура
```
src/
  bot/
    main.py       # хендлеры и запуск
    orders.py     # DB-операции с заявками
  database/
    db.py         # инициализация БД
  content/
    content.py    # весь контент (услуги, портфолио, FAQ, калькулятор)
data/
  lotos.db        # SQLite (создаётся автоматически)
```

## Запуск

```bash
pip install -r requirements.txt
cp .env.example .env
# Вставить токен в .env
python -m src.bot.main
```

## Функции
- /start — главное меню
- Услуги и цены
- Портфолио
- Форма заявки (ConversationHandler) — приходит алерт в Telegram с кнопками
- Калькулятор стоимости
- FAQ
- /orders — список заявок (только для админа)
