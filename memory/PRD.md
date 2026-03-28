# AI Trading Signal Screener - PRD

## Original Problem Statement
Telegram бот для автоматического мониторинга торговых сигналов из Tradium [WORKSPACE] Trade Setup Screener. Парсит сигналы, AI распознаёт DCA #4 с графика, мониторит цену, отправляет оповещение + график когда цена достигает DCA #4.

## Architecture
- **server.py** (FastAPI): API + запускает 3 воркера как subprocess
  - signal_monitor.py → Telethon → Tradium topic 3204 → парсит → AI DCA#4 → сохраняет молча
  - entry_monitor.py → мониторит цены (Kraken/OKX) → DCA#4 alert + TP/SL tracking
  - telegram_bot.py → /start /signals /entries /stats /help
- Frontend: React (тёмный терминальный дашборд)
- DB: **MongoDB Atlas** (cluster0.vs1rsll.mongodb.net)

## What's Implemented
- ✅ Telethon → Tradium [WORKSPACE] topic 3204
- ✅ Парсер Tradium формата (Short/Long)
- ✅ GPT-5.2 Vision DCA#4 extraction (ImageContent base64)
- ✅ Entry monitor (DCA#4 + TP/SL + 0.3% tolerance)
- ✅ Telegram оповещения + график
- ✅ Воркеры из server.py (переживают деплой)
- ✅ MongoDB Atlas (данные персистентны)
- ✅ React админка (Сигналы / Выполненные)
- ✅ API: /signals, /entries, /entries/stats

## Tested (28 Mar 2026)
- ✅ E2E на Atlas: watching → DCA#4 hit → Telegram alert + photo → DB updated
- ✅ SHORT trigger, LONG trigger, НЕ-trigger — все верно
- ✅ Парсер: 5 форматов
- ✅ API все поля (dca4_level, timeframe, trend)
- ✅ Фронтенд обе вкладки

## Backlog
### P1
- [ ] Webhook для автоматической торговли
### P2
- [ ] MEXC/KuCoin для редких альткоинов
- [ ] Historical performance tracking
