# AI Trading Signal Screener - PRD

## Original Problem Statement
Создать Telegram бота для фильтрации и AI-анализа торговых сигналов. Бот должен читать сигналы из закрытого Telegram бота (через Telethon user account), анализировать их с помощью GPT-5.2 используя данные Binance Futures, и отправлять отфильтрованные сигналы.

## User Personas
- **Трейдер**: Получает сигналы от разных источников, хочет автоматически фильтровать их по качеству
- **Администратор**: Настраивает параметры фильтрации и управляет ботом

## Core Requirements (Static)
1. Чтение сигналов из Telegram (Telethon MTProto API)
2. Анализ с GPT-5.2 (технический анализ, R/R, тренд)
3. Данные с Binance Futures (OHLCV, объемы, индикаторы)
4. Фильтрация по критериям (min R/R, объемы, тренд)
5. Dashboard со статистикой
6. Настройки через веб-интерфейс

## What's Been Implemented (26 Jan 2026)
### Backend
- ✅ FastAPI сервер с MongoDB
- ✅ GPT-5.2 интеграция через emergentintegrations
- ✅ Binance Futures API для рыночных данных
- ✅ Технические индикаторы (RSI, EMA, MACD, Bollinger Bands)
- ✅ Парсинг сигналов (множественные форматы)
- ✅ AI анализ с структурированным ответом
- ✅ CRUD для сигналов и настроек
- ✅ Статистика и данные для графиков

### Frontend
- ✅ Dashboard с KPI карточками
- ✅ График статистики за 7 дней (Recharts)
- ✅ Таблица сигналов с AI confidence
- ✅ Ручной анализ сигналов
- ✅ Страница настроек (Telegram, фильтры)
- ✅ Переключатель статуса бота

### Integrations
- ✅ GPT-5.2 (OpenAI via Emergent LLM Key)
- ✅ Binance Futures API (market data)
- ⏸️ Telethon (configured, requires user API credentials)
- ⏸️ Telegram Bot (configured, token provided)

## Prioritized Backlog

### P0 (Critical)
- [x] AI signal analysis
- [x] Market data from Binance
- [x] Web dashboard
- [x] Settings management

### P1 (High)
- [ ] Telethon live signal monitoring (requires user's my.telegram.org credentials)
- [ ] Telegram bot notifications for filtered signals
- [ ] Real-time WebSocket updates

### P2 (Medium)
- [ ] Historical performance tracking (did signal hit TP/SL?)
- [ ] Multiple signal source chats
- [ ] Custom AI prompts per symbol
- [ ] Backtesting mode

## Next Tasks
1. Получить Telegram API ID и Hash от пользователя (my.telegram.org)
2. Реализовать live мониторинг через Telethon
3. Настроить отправку отфильтрованных сигналов в бот
4. Добавить WebSocket для real-time обновлений на dashboard

## Technical Notes
- Binance API может быть недоступен в некоторых регионах (error 451)
- AI анализ работает даже без рыночных данных (с ограниченной точностью)
- Telegram Bot Token: `8558977408:AAHDyFx9KR-_u-apKjPH6wgeYq_qln2YX3U`
