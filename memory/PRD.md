# Tradium Signal Monitor — PRD

## Оригинальная задача
Автоматический скринер трейдинг-сигналов из Telegram-канала Tradium. AI анализирует графики через GPT-5.2 Vision, извлекает DCA #4 уровни. Мониторит цену в реальном времени, ждёт разворотную свечу после DCA #4, и только тогда отправляет подтверждённый сигнал входа.

## Архитектура
- **Backend**: FastAPI (server.py) + фоновые скрипты (signal_monitor.py, entry_monitor.py, telegram_bot.py)
- **Frontend**: React (Dark trading theme, 3 вкладки)
- **DB**: MongoDB Atlas
- **Integrations**: GPT-5.2 Vision (Emergent LLM Key), Telethon, python-telegram-bot, CCXT (Kraken)

## Что реализовано

### Core
- [x] Telethon клиент читает сигналы из Tradium [WORKSPACE] topic 3204
- [x] AI Vision (GPT-5.2) извлекает DCA уровни с графиков
- [x] Двухэтапное подтверждение входа (DCA#4 + разворотная свеча)
- [x] 8 свечных паттернов (candle_patterns.py)
- [x] Background scripts через subprocess в FastAPI startup
- [x] MongoDB Atlas

### Admin Panel (React) — 3 вкладки
- [x] **Сигналы Tradium** — watching, dca4_reached
- [x] **Подтверждённые** — entered (с паттерном, силой, ценой входа)
- [x] **Выполненные** — entry_signals (OPEN, TP_HIT, SL_HIT с P&L)
- [x] Stats pills: Сигналы, Слежу, DCA#4, Открыто, TP, SL, Win Rate
- [x] Модальное окно с графиком, DCA уровнями, паттерном разворота

### Telegram Bot — 3 кнопки
- [x] "📋 Сигналы" — список сигналов Tradium
- [x] "🕯 Подтверждённые" — входы после разворотной свечи
- [x] "🎯 Выполненные" — закрытые позиции

## Поток статусов
`watching` → `dca4_reached` → `entered` → `tp_hit` / `sl_hit`

## Backlog
- [ ] P1: AI распознавание точек входа прямо с картинок (без текста)
- [ ] P2: Webhook для автоматического исполнения сделок

## Файлы
- `/app/backend/candle_patterns.py` — детекция свечных паттернов
- `/app/backend/entry_monitor.py` — v4 двухэтапное подтверждение
- `/app/backend/signal_monitor.py` — парсер Tradium + AI Vision
- `/app/backend/telegram_bot.py` — бот с 3 кнопками
- `/app/backend/server.py` — FastAPI + worker management
- `/app/frontend/src/App.js` — React админка с 3 вкладками
