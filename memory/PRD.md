# AI Trading Signal Screener - PRD

## Original Problem Statement
Telegram бот для фильтрации и AI-анализа торговых сигналов из Tradium [WORKSPACE] Trade Setup Screener. Бот читает сигналы из приватной подгруппы (topic 3204), анализирует текст и графики с помощью GPT-5.2 vision, и отправляет результат анализа пользователю.

## Architecture
- **signal_monitor.py** (Supervisor): Telethon → читает Tradium topic 3204 → парсит сетапы → скачивает графики → GPT-5.2 vision анализ → отправляет результат
- **telegram_bot.py** (Supervisor): Бот @cryptosignal1mybot → ручной анализ (Tradium + legacy форматы) → команды /start /signals /entries /stats
- **entry_monitor.py** (Supervisor): Мониторинг цен через Kraken/OKX → алерты при достижении Entry/TP/SL
- **pro_analyzer.py**: Модуль глубокого AI анализа (технический + новости + сентимент + CoinGecko) — для legacy формата
- **server.py**: FastAPI API для веб-дашборда

## Signal Source
- **Channel**: Tradium [WORKSPACE] (ID: -1002423680272)
- **Topic**: Trade Setup Screener (topic_id: 3204)
- **Format**: Structured text (#сетап) + TradingView chart images
- **Fields**: Symbol, Direction (Long/Short), Entry, TP, SL, R:R, Trend indicators, MA, RSI, Volume, Key levels

## What's Been Implemented
### Core (Done)
- ✅ Telethon подключение к Tradium [WORKSPACE] topic 3204
- ✅ Парсер Tradium Setup Screener формата ($SYMBOL, Entry/TP/SL, TREND, MA/RSI, Volume, Key levels)
- ✅ Скачивание графиков (photo pairing: photo ID+1 → text ID)
- ✅ GPT-5.2 Vision анализ (текст + график через base64 ImageContent)
- ✅ Отправка результатов AI анализа пользователям бота
- ✅ Supervisor конфигурации для всех 3 скриптов (автоперезапуск)
- ✅ Миграция с Binance → Kraken/CCXT (Error 451 fix)
- ✅ Entry monitor (мониторинг цен, алерты TP/SL)
- ✅ Telegram бот с кнопками (Сигналы, Вход, Статистика)
- ✅ Веб-дашборд (React + Shadcn)

### Integrations
- ✅ GPT-5.2 with Vision (OpenAI via Emergent LLM Key) — текст + изображения
- ✅ Telethon (Telegram User API) → Tradium [WORKSPACE]
- ✅ Telegram Bot API → @cryptosignal1mybot
- ✅ Kraken/OKX API (CCXT) — рыночные данные
- ✅ CoinGecko API — фундаментальные данные

## Prioritized Backlog

### P1 (High)
- [ ] Webhook для автоматической торговли

### P2 (Medium)
- [ ] MEXC/KuCoin для редких альткоинов
- [ ] Historical performance tracking
- [ ] WebSocket обновления на дашборде

### P3 (Low)
- [ ] Custom AI промпты
- [ ] Backtesting mode

## Technical Notes
- Binance API заблокирован (Error 451) — используем Kraken/OKX
- OpenAI FileContentWithMimeType НЕ работает — используем ImageContent(image_base64=...)
- Photo pairing: в Tradium фото приходит с ID = text_msg_id + 1
- Telegram 2FA: 1240Maxim
- Bot Token: 8558977408:AAHDyFx9KR-_u-apKjPH6wgeYq_qln2YX3U
