# Tradium Signal Monitor — PRD

## Оригинальная задача
Автоматический скринер трейдинг-сигналов из Telegram-канала Tradium. AI анализирует графики через GPT-5.2 Vision, извлекает DCA #4 уровни. Двухэтапное подтверждение: DCA#4 достигнут → разворотная свеча → сигнал входа.

## Архитектура
- **Backend**: FastAPI (server.py) + фоновые скрипты (signal_monitor, entry_monitor, telegram_bot)
- **Frontend**: React (Dark trading theme, 4 вкладки)
- **DB**: MongoDB Atlas
- **Integrations**: GPT-5.2 Vision (Emergent LLM Key), Telethon, python-telegram-bot, CCXT (Kraken)

## Что реализовано

### Admin Panel — 4 вкладки (все с модалкой)
- [x] **Tradium** — входящие сигналы (watching)
- [x] **DCA#4** — цена достигла DCA#4, ждём разворот (dca4_reached)
- [x] **Вход + Разворот** — подтверждённые разворотной свечой (entered)
- [x] **Результаты** — закрытые позиции (TP_HIT, SL_HIT, OPEN)
- [x] Модальное окно на каждой вкладке с графиком и деталями

### Telegram Bot — 4 кнопки (2x2 grid)
- [x] "📋 Tradium" — входящие
- [x] "📍 DCA#4" — ждём разворот
- [x] "🕯 Вход+Разворот" — подтверждённые
- [x] "📊 Результаты" — TP/SL

### Core Logic
- [x] Двухэтапное подтверждение (DCA#4 + 8 свечных паттернов)
- [x] 2 уведомления: при DCA#4 и при разворотной свече
- [x] TP/SL мониторинг

## Поток статусов
`watching` → `dca4_reached` → `entered` → `tp_hit` / `sl_hit`

## Backlog
- [ ] P1: AI распознавание точек входа с картинок
- [ ] P2: Webhook для автоматического исполнения сделок
