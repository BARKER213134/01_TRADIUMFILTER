# Tradium Signal Monitor — PRD

## Оригинальная задача
Автоматический скринер трейдинг-сигналов из Telegram-канала Tradium. AI анализирует графики через GPT-5.2 Vision, извлекает DCA #4 уровни. Двухэтапное подтверждение: DCA#4 достигнут → разворотная свеча → сигнал входа.

## Архитектура
- **Backend**: FastAPI (server.py) + фоновые asyncio tasks (signal_monitor, entry_monitor, telegram_bot)
- **Frontend**: React (Dark trading theme, 4 вкладки)
- **DB**: MongoDB Atlas
- **Integrations**: GPT-5.2 Vision (Emergent LLM Key), Telethon, python-telegram-bot, CCXT (Kraken)

## Что реализовано

### Admin Panel — 4 вкладки
- [x] **Tradium** — входящие сигналы (watching)
- [x] **DCA#4** — цена достигла DCA#4, ждём разворот (dca4_reached)
- [x] **Вход + Разворот** — подтверждённые разворотной свечой (entered)
- [x] **Результаты** — закрытые позиции (TP_HIT, SL_HIT, OPEN)
- [x] Модальное окно с графиком и деталями
- [x] Batch deletion и checkbox selection

### Telegram Bot — 4 кнопки (2x2 grid)
- [x] "📋 Tradium" — входящие
- [x] "📍 DCA#4" — ждём разворот
- [x] "🕯 Вход+Разворот" — подтверждённые
- [x] "📊 Результаты" — TP/SL

### Core Logic
- [x] Двухэтапное подтверждение (DCA#4 + 8 свечных паттернов)
- [x] 2 уведомления: при DCA#4 и при разворотной свече
- [x] TP/SL мониторинг
- [x] **Environment isolation**: Preview pod НЕ запускает Telegram воркеры → нет конфликтов с production (Fixed 2026-03-30)

### Environment Isolation (P0 fix)
- [x] `is_preview_env()` в server.py — определяет preview по APP_URL и /opt/plugins-venv
- [x] Preview: API + UI работают, воркеры отключены
- [x] Production: все воркеры запускаются автоматически
- [x] `/api/health` показывает режим (preview/production)

## Поток статусов
`watching` → `dca4_reached` → `entered` → `tp_hit` / `sl_hit`

## Backlog
- [ ] P1: Webhook для автоматического исполнения сделок
- [ ] P2: AI распознавание точек входа с картинок
