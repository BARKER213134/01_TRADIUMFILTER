# AI Trading Signal Screener - PRD

## Original Problem Statement
Telegram бот для автоматического мониторинга торговых сигналов из Tradium [WORKSPACE] Trade Setup Screener. Бот парсит сигналы, AI распознаёт DCA #4 уровень с графика, мониторит цену, и отправляет красивое оповещение с графиком когда цена достигает DCA #4.

## Architecture
- **server.py** (FastAPI + Workers): API + запускает все 3 воркера как subprocess при старте
  - signal_monitor.py → Telethon → Tradium topic 3204 → парсит → AI DCA#4 → сохраняет молча
  - entry_monitor.py → мониторит цены → DCA#4 alert + TP/SL tracking
  - telegram_bot.py → /start /signals /entries /stats
- Frontend: React (тёмный терминальный дашборд)

## Signal Flow
1. Tradium → сигнал (текст + фото) → signal_monitor парсит
2. GPT-5.2 Vision → извлекает DCA #1-5 + зону с графика
3. Сохраняет в MongoDB: status="watching", dca4_level, chart_path
4. entry_monitor каждые 10с проверяет цену:
   - SHORT: цена >= DCA#4 → alert "ВХОД В ШОРТ" + график
   - LONG: цена <= DCA#4 → alert "ВХОД В ЛОНГ" + график
5. Потом мониторит TP/SL → alert при закрытии

## What's Been Implemented
- ✅ Telethon → Tradium [WORKSPACE] topic 3204
- ✅ Парсер Tradium формата
- ✅ GPT-5.2 Vision извлечение DCA#4 (ImageContent base64)
- ✅ Сохранение графиков в /app/backend/charts/
- ✅ Entry monitor v3 (DCA#4 + TP/SL + tolerance 0.3%)
- ✅ Красивые Telegram оповещения + график снизу
- ✅ Telegram бот v3 (только команды, ручной режим убран)
- ✅ Воркеры запускаются из server.py (переживают деплой)
- ✅ React админка (2 вкладки: Сигналы / Выполненные)

## Tested
- ✅ Парсинг Tradium → DCA#4 extraction с реальных графиков
- ✅ Entry monitor: ETH DCA#4=2024 → triggered @ 2024.53 → sendMessage/sendPhoto 200 OK
- ✅ Воркеры стартуют из FastAPI и перезапускаются при падении
- ✅ API endpoints: /signals, /entries, /entries/stats работают

## Prioritized Backlog
### P1
- [ ] Webhook для автоматической торговли
### P2
- [ ] MEXC/KuCoin для редких альткоинов
- [ ] Historical performance tracking
