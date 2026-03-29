# Tradium Signal Monitor — PRD

## Оригинальная задача
Автоматический скринер трейдинг-сигналов из Telegram-канала Tradium. AI анализирует графики через GPT-5.2 Vision, извлекает DCA #4 уровни. Мониторит цену в реальном времени, ждёт разворотную свечу после DCA #4, и только тогда отправляет подтверждённый сигнал входа.

## Архитектура
- **Backend**: FastAPI (server.py) + фоновые скрипты (signal_monitor.py, entry_monitor.py, telegram_bot.py)
- **Frontend**: React (Dark trading theme, 2 вкладки)
- **DB**: MongoDB Atlas
- **Integrations**: GPT-5.2 Vision (Emergent LLM Key), Telethon, python-telegram-bot, CCXT (Kraken)

## Что реализовано

### Core
- [x] Telethon клиент читает сигналы из Tradium [WORKSPACE] topic 3204
- [x] AI Vision (GPT-5.2) извлекает DCA уровни с графиков
- [x] **Двухэтапное подтверждение входа:**
  - Stage 1: Цена достигает DCA #4 → статус `dca4_reached` → уведомление "Жду разворот"
  - Stage 2: Разворотная свеча обнаружена → статус `entered` → ПОДТВЕРЖДЁННЫЙ СИГНАЛ ВХОДА
- [x] Свечные паттерны (candle_patterns.py): Молот, Падающая звезда, Доджи (3 типа), Бычье/Медвежье поглощение, Утренняя/Вечерняя звезда, Пин-бар
- [x] Telegram бот с 2 кнопками: "📋 Сигналы" и "🎯 Выполненные"
- [x] Background scripts через subprocess в FastAPI startup
- [x] MongoDB Atlas

### Admin Panel (React)
- [x] Dark trading theme
- [x] 2 вкладки: "Сигналы Tradium" и "Выполненные"
- [x] Stats pills: Сигналы, Слежу, DCA#4, Открыто, TP, SL, Win Rate
- [x] Кликабельные строки → модальное окно с графиком, DCA уровнями, разворотным паттерном
- [x] API для chart images

## Поток статусов сигнала
`watching` → `dca4_reached` → `entered` → `tp_hit` / `sl_hit`

## Backlog
- [ ] P1: AI распознавание точек входа прямо с картинок (без текста)
- [ ] P2: Webhook для автоматического исполнения сделок

## API Endpoints
- `GET /api/signals` — список сигналов
- `GET /api/entries` — выполненные сигналы
- `GET /api/entries/stats` — статистика (включая dca4_reached)
- `GET /api/charts/{filename}` — chart images
- `GET /api/signals/{signal_id}/chart` — chart filename по signal ID

## DB Schema
- `signals`: {id, symbol, direction, dca4_level, timeframe, trend, entry_price, take_profit, stop_loss, rr_ratio, status, chart_path, dca_data, reversal_pattern, pattern_strength, pattern_candle, timestamp}
- `entry_signals`: {signal_id, symbol, direction, entry_price, dca4_level, take_profit, stop_loss, rr_ratio, chart_path, reversal_pattern, pattern_strength, triggered_at, status}
- `bot_users`: {chat_id, registered}

## Файлы
- `/app/backend/candle_patterns.py` — модуль детекции свечных паттернов
- `/app/backend/entry_monitor.py` — v4 с двухэтапным подтверждением
- `/app/backend/signal_monitor.py` — парсер Tradium + AI Vision
- `/app/backend/telegram_bot.py` — бот с 2 кнопками
- `/app/backend/server.py` — FastAPI + worker management
- `/app/frontend/src/App.js` — React админка
