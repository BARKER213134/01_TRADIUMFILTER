# AI Trading Signal Screener - PRD

## Original Problem Statement
Создать Telegram бота для фильтрации и AI-анализа торговых сигналов. Бот читает сигналы из закрытого бота @cvizor_bot (через Telethon user account), анализирует с помощью GPT-5.2 (технический анализ, новости, R:R, объёмы через Kraken/CoinGecko), и отправляет отфильтрованные сигналы пользователю.

## Architecture
- **signal_monitor.py** (Supervisor): Telethon клиент → читает @cvizor_bot → анализирует через pro_analyzer → шлёт результат в Telegram
- **telegram_bot.py** (Supervisor): Пользовательский бот @cryptosignal1mybot → команды /start /signals /entries /stats + ручной анализ
- **entry_monitor.py** (Supervisor): Фоновый цикл → проверяет цены через Kraken/OKX → алертит при достижении точки входа / TP / SL
- **pro_analyzer.py**: Модуль глубокого AI анализа (технический + новости + сентимент + CoinGecko)
- **server.py**: FastAPI API для веб-дашборда
- Frontend: React + Shadcn UI дашборд

## What's Been Implemented
### Done (26 Jan - 26 Mar 2026)
- ✅ FastAPI + React + MongoDB архитектура
- ✅ GPT-5.2 интеграция через emergentintegrations (Emergent LLM Key)
- ✅ Telethon автоматическое чтение @cvizor_bot (авторизация через 2FA)
- ✅ Парсинг 5+ форматов сигналов (emoji, пробои, RSI)
- ✅ pro_analyzer.py: глубокий AI анализ (технический + новости + сентимент)
- ✅ entry_monitor.py: мониторинг цен + алерты TP/SL
- ✅ Миграция с Binance (451 blocked) → Kraken + CoinGecko + OKX fallback
- ✅ Telegram бот с кнопками: Сигналы, Вход, Статистика
- ✅ Веб-дашборд со статистикой

### Fixed (26 Mar 2026)
- ✅ **Supervisor конфигурации** для telegram_bot, signal_monitor, entry_monitor — процессы автоматически перезапускаются
- ✅ **Удалён Binance** из всех файлов (telegram_bot.py, signal_monitor.py, server.py) → заменён на ccxt/Kraken
- ✅ **Telethon сессия** жива — бот подключен к @cvizor_bot и ожидает сигналы
- ✅ Очистка ненужных файлов (telethon_auth.py, tg_step*.py)

## Integrations
- ✅ GPT-5.2 (OpenAI via Emergent LLM Key)
- ✅ Telegram Bot API (token в .env)
- ✅ Telethon (Telegram User API)
- ✅ Kraken API (CCXT, публичный)
- ✅ CoinGecko API (публичный)
- ✅ OKX API (CCXT fallback, публичный)

## Prioritized Backlog

### P1 (High)
- [ ] Webhook для автоматической торговли ("потом будем делать под вебхук")

### P2 (Medium)
- [ ] Добавить MEXC/KuCoin для редких альткоинов
- [ ] Historical performance tracking (TP/SL результаты)
- [ ] Multiple signal source chats
- [ ] Real-time WebSocket обновления на дашборде

### P3 (Low)
- [ ] Custom AI промпты по символу
- [ ] Backtesting mode

## Technical Notes
- Binance API заблокирован (Error 451) — используем Kraken/OKX
- Telegram 2FA пароль: 1240Maxim
- Bot Token: 8558977408:AAHDyFx9KR-_u-apKjPH6wgeYq_qln2YX3U
- Telethon сессия: /app/backend/telethon_session.session
