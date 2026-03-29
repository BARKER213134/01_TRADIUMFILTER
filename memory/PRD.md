# Tradium Signal Monitor — PRD

## Оригинальная задача
Автоматический скринер трейдинг-сигналов из Telegram-канала Tradium. AI анализирует графики через GPT-5.2 Vision, извлекает DCA #4 уровни. Мониторит цену в реальном времени и отправляет alert в Telegram когда цена достигает DCA #4.

## Архитектура
- **Backend**: FastAPI (server.py) + фоновые скрипты (signal_monitor.py, entry_monitor.py, telegram_bot.py)
- **Frontend**: React (Dark trading theme, 2 вкладки)
- **DB**: MongoDB Atlas
- **Integrations**: GPT-5.2 Vision (Emergent LLM Key), Telethon, python-telegram-bot, CCXT (Kraken)

## Что реализовано

### Core
- [x] Telethon клиент читает сигналы из Tradium [WORKSPACE] topic 3204
- [x] AI Vision (GPT-5.2) извлекает DCA уровни с графиков
- [x] Entry monitor отслеживает цену через CCXT (Kraken) и алертит при DCA #4
- [x] Telegram бот отправляет алерты (без ручного управления)
- [x] Background scripts запускаются через subprocess в FastAPI startup
- [x] MongoDB Atlas для персистенции данных

### Admin Panel (React)
- [x] Dark trading theme
- [x] 2 вкладки: "Сигналы Tradium" и "Выполненные"
- [x] Stats pills в хедере (Сигналы, Слежу, Открыто, TP, SL, Win Rate)
- [x] Кликабельные строки таблицы → модальное окно с деталями
- [x] Модальное окно: график (chart image), DCA уровни, AI анализ, все параметры сигнала
- [x] API endpoint для отдачи chart images

### Telegram Bot
- [x] 2 кнопки: "📋 Сигналы" и "🎯 Выполненные" (ReplyKeyboardMarkup)
- [x] Команды: /start, /help, /signals, /entries
- [x] Бот-аватар с "PROFIT +238%"

## Backlog (Будущие задачи)
- [ ] P1: AI распознавание точек входа прямо с картинок (без текста)
- [ ] P2: Webhook для автоматического исполнения сделок

## API Endpoints
- `GET /api/signals` — список сигналов
- `GET /api/entries` — выполненные сигналы
- `GET /api/entries/stats` — статистика
- `GET /api/charts/{filename}` — chart images
- `GET /api/signals/{signal_id}/chart` — chart filename по signal ID

## DB Schema
- `signals`: {id, symbol, direction, dca4_level, timeframe, trend, entry_price, take_profit, stop_loss, rr_ratio, status, chart_path, dca_data, timestamp, ...}
- `entry_signals`: {signal_id, symbol, direction, entry_price, tp_price, sl_price, status, triggered_at, ...}
- `bot_users`: {chat_id, registered}
