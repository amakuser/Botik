# Agent Memory — dashboard-dev

> Читать перед началом работы. Обновлять после каждой нетривиальной задачи.

---

## Non-trivial solutions

### 2026-04-18 — Миграция pywebview → Tauri + React

**Проблема:** Весь UI был в одном `dashboard_preview.html` (single-file SPA) + pywebview bridge.
Задача: мигрировать на React 19 + TypeScript + Vite + Tauri, сохранив функциональность.

**Решение:**
- Удалены все 22 файла `src/botik/gui/` + dashboard_preview.html
- `windows_entry.py` переписан: запускает Tauri exe как subprocess + app-service
- Новые страницы: Settings, Market, Orderbook, Backtest добавлены в React
- `frontend/src/app/router.tsx` — 14 роутов
- Транспорт Python↔JS: теперь через HTTP API (app-service), не pywebview bridge

**Вывод:** При добавлении новых API методов — редактировать app-service, не pywebview.
Структура: `frontend/src/features/<name>/<Name>Page.tsx`

---

### 2026-03-22 — Разбивка webview_app.py на миксины

**Проблема:** webview_app.py вырос до 1849 строк — нечитаем.

**Решение:** Разбит на 8 модулей:
- `api_helpers.py` — ROOT_DIR, пути, _load_yaml
- `api_db_mixin.py` — SQL-хелперы
- `api_models_mixin.py` — ML статус
- `api_spot_mixin.py` — spot UI
- `api_futures_mixin.py` — futures UI
- `api_system_mixin.py` — snapshot, logs, ops
- `api_settings_mixin.py` — .env + проверки
- `api_trading_mixin.py` — start/stop trading & ML

`webview_app.py` стал тонкой точкой входа ~200 строк.

**Вывод:** Новые API методы добавлять в профильный `api_*_mixin.py`, не в корневой файл.

---

### 2026-03-21 — Schema introspection вместо жёстких колонок

**Проблема:** Разные версии БД имеют разные имена колонок:
- `futures_positions`: `size` vs `qty`, `unrealised_pnl` vs `unrealized_pnl`
- `spot_holdings`: новые колонки отличаются от legacy

**Решение:** Introspection через `PRAGMA table_info(table_name)` — определять доступные
колонки динамически, строить SELECT из того что есть.

```python
def _get_columns(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}
```

**Вывод:** Никогда не хардкодить имена колонок для таблиц с историей миграций.

---

## Quirks & gotchas

- **Tauri hot reload:** `pnpm dev` работает только если app-service запущен. При отсутствии
  сервиса страницы загружаются но API calls висят.
- **React роутер:** Используется `react-router-dom` v7. Lazy imports через `lazy()` + `Suspense`.
- **CSS архитектура:** `app.css` (BEM) и Tailwind v4 сосуществуют. Новые компоненты —
  Tailwind через `cn()`. Старые BEM классы не трогать.
- **Dev Tools:** Скриншоты через `GET http://localhost:9989/screenshot`. Навигация через
  `POST http://localhost:9989/navigate {"tab": "<страница>"}`.

---

## Current context

**Последняя задача:** Миграция GUI на Tauri+React (2026-04-18) — ✅ выполнено
**Ожидает:** UI-Foundation (Tailwind v4 + shadcn/ui + Framer Motion + Inter font + UI Lab)
**Задание:** Полная спецификация в `AGENTS_CONTEXT.md` → ## Архив заданий → UI-Foundation

### 2026-04-19 — Верификация: структура файла памяти подтверждена

Проверка в рамках Memory Enforcement System. Структура соответствует протоколу:
- ## Non-trivial solutions ✅
- ## Quirks & gotchas ✅
- ## Current context ✅

Файл доступен для чтения агентом перед задачей.
