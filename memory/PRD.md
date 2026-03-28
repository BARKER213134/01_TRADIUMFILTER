# AI Trading Signal Screener - PRD

## Original Problem Statement
Telegram бот для автоматического мониторинга торговых сигналов из Tradium [WORKSPACE] Trade Setup Screener. Бот парсит сигналы, AI распознаёт DCA #4 уровень с графика, мониторит цену, и отправляет красивое оповещение с графиком когда цена достигает DCA #4.

## Architecture
- **signal_monitor.py** (Supervisor): Telethon → Tradium topic 3204 → парсит сетап → AI Vision извлекает DCA#4 с графика → сохраняет в базу МОЛЧА
- **entry_monitor.py** (Supervisor): Мониторит цену каждые 10 сек → при достижении DCA#4 отправляет красивое оповещение + график → потом следит за TP/SL
- **telegram_bot.py** (Supervisor): Только команды: /start /signals /entries /stats (ручной режим убран)
- **server.py**: FastAPI API
- Frontend: React (дашборд)

## Signal Flow
1. Tradium → сигнал (текст + фото графика) → signal_monitor парсит
2. GPT-5.2 Vision анализирует график → извлекает DCA #1-5, зону RESISTANCE/SUPPORT
3. Сохраняет: symbol, direction, DCA#4 level, chart image → status: "watching"
4. entry_monitor проверяет цену:
   - SHORT: цена >= DCA#4 → "ВХОД В ШОРТ" + график
   - LONG: цена <= DCA#4 → "ВХОД В ЛОНГ" + график
5. После входа следит за TP/SL → оповещение при закрытии

## DCA#4 Logic
- **SHORT**: DCA уровни идут ВВЕРХ к RESISTANCE. DCA#4 возле сопротивления. SL за сопротивлением.
- **LONG**: DCA уровни идут ВНИЗ к SUPPORT. DCA#4 возле поддержки. SL за поддержкой.

## What's Been Implemented
- ✅ Telethon → Tradium [WORKSPACE] topic 3204
- ✅ Парсер Tradium формата (Short/Long, Entry/TP/SL, R:R, Trend, MA/RSI)
- ✅ GPT-5.2 Vision извлечение DCA#4 с графиков (base64 ImageContent)
- ✅ Сохранение графиков в /app/backend/charts/
- ✅ Entry monitor v3 — следит за DCA#4 с tolerance 0.3%
- ✅ Красивые оповещения с DCA уровнями + график
- ✅ TP/SL алерты с P&L расчётом
- ✅ Telegram бот v3 (только команды, без ручного режима)
- ✅ Supervisor для всех 3 скриптов

## Integrations
- ✅ GPT-5.2 with Vision (Emergent LLM Key)
- ✅ Telethon → Tradium [WORKSPACE]
- ✅ Telegram Bot API → @cryptosignal1mybot
- ✅ Kraken/OKX API (CCXT) — мониторинг цен

## Prioritized Backlog

### P1
- [ ] Webhook для автоматической торговли

### P2
- [ ] MEXC/KuCoin для редких альткоинов
- [ ] Historical performance tracking
- [ ] WebSocket обновления на дашборде

### P3
- [ ] Backtesting mode

## Technical Notes
- Binance API заблокирован (Error 451)
- OpenAI FileContentWithMimeType НЕ работает — используем ImageContent(image_base64=...)
- Photo pairing: фото msg_id = text msg_id + 1
- Charts saved to: /app/backend/charts/
- Telegram 2FA: 1240Maxim
- Bot Token: 8558977408:AAHDyFx9KR-_u-apKjPH6wgeYq_qln2YX3U
