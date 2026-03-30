# Tradium Signal Monitor — PRD

## Оригинальная задача
Автоматический скринер трейдинг-сигналов из Telegram-канала Tradium. AI анализирует графики через GPT-5.2 Vision, извлекает DCA #4 уровни. Двухэтапное подтверждение: DCA#4 достигнут → разворотная свеча → сигнал входа.

## Архитектура
- **Backend**: FastAPI (server.py) + фоновые asyncio tasks с MongoDB leader election
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
- [x] TP/SL мониторинг — одно уведомление на сигнал

### Infrastructure (Fixed 2026-03-30)
- [x] **MongoDB Leader Election** — только один экземпляр запускает воркеры, автоматический failover
- [x] Дедупликация entry_signals и signal_monitor
- [x] TP/SL группировка по signal_ref
- [x] Telethon session пересоздана после AuthKeyDuplicatedError

## Поток статусов
`watching` → `dca4_reached` → `entered` → `tp_hit` / `sl_hit`

## Leader Election
- Каждый экземпляр генерирует уникальный instance_id
- Пытается захватить `leader_lock` в MongoDB каждые 15 сек
- TTL лока = 45 сек, лидер обновляет его регулярно
- Если лидер умирает, лок истекает и другой экземпляр подхватывает
- `/api/health` показывает текущего лидера и статус

## Backlog
- [ ] P1: Webhook для автоматического исполнения сделок
- [ ] P2: AI распознавание точек входа с картинок
