# AGENTS_CONTEXT.md — Общая доска агентов

> **ПРОТОКОЛ (обязательно):**
> 1. Оркестратор ВСЕГДА пишет задачу сюда ДО запуска агентов
> 2. Каждый агент читает этот файл ПЕРВЫМ — до любых других действий
> 3. Агент пишет статус "🔄 в работе" сразу при старте
> 4. Агент пишет результат сюда ПЕРЕД тем как завершить работу
> 5. Оркестратор сбрасывает ## Задания и ## Статусы в начале новой задачи

---

## Текущая задача

**Задача:** Memory Enforcement System — ✅ выполнено 2026-04-19

**Что сделано:**
- SESSION_LOG.md, progress.md созданы
- .claude/agents/memory/*.md созданы (dashboard-dev, trading-expert, ml-researcher)
- CLAUDE.md обновлён (Memory Enforcement раздел)
- Стейл SESSION_CHECKPOINT.json удалён
- solutions/ пополнен (2 файла)

---

## Задания

*Нет активных заданий. Доска готова к следующей задаче.*

---

## Статусы

| Агент | Статус | Завершён |
|-------|--------|----------|
| переводчик | ✅ завершён | 2026-04-18 |
| UI-Foundation | ⏸ ожидает запуска | — |

> UI-Foundation: задание подготовлено, агент НЕ запускался. Спецификация — в ## Архив заданий ниже.

---

## Архив заданий

### UI-Foundation ⏸ — ожидает запуска

**Статус:** Задание написано 2026-04-18. Агент НЕ запускался. Готово к запуску.

**Задача:** Создать premium UI-систему для Botik (React/Tauri frontend).

**Контекст:**
- Фронтенд: `C:\ai\aiBotik\frontend\`
- Кастомный CSS (`frontend/src/styles/app.css`, 2000+ строк, BEM-style)
- CSS-переменные: `--surface-bg`, `--text-primary`, `--accent-strong` (#d7cbb1) — уже есть
- Тёмная тема, glassmorphic поверхности, warm accent palette
- НЕТ Tailwind, shadcn/ui, Framer Motion, icon library
- 16 роутов, feature-based структура

**Важно:**
- НЕ ломать существующий CSS — он рабочий
- Tailwind v4 добавить РЯДОМ с app.css, не вместо него
- shadcn/ui использовать для НОВЫХ компонентов
- Существующие BEM классы оставить как есть

---

#### ЧАСТЬ 1 — Tailwind v4

```bash
cd C:\ai\aiBotik\frontend
npm install tailwindcss @tailwindcss/vite
```

Обнови `vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1", port: 4173 },
});
```

Добавь в начало `frontend/src/styles/app.css`:
```css
@import "tailwindcss";
```

#### ЧАСТЬ 2 — Design Tokens

Создай `frontend/src/styles/tokens.css`:
```css
@layer base {
  :root {
    --token-bg-base: 5 7 11;
    --token-bg-surface: 14 18 24;
    --token-bg-panel: 18 22 28;
    --token-bg-subtle: 15 23 42;
    --token-border-default: 201 209 220 / 0.12;
    --token-border-strong: 215 203 177 / 0.22;
    --token-border-accent: 215 203 177 / 0.38;
    --token-text-primary: 237 241 247;
    --token-text-secondary: 174 184 199;
    --token-text-muted: 125 136 152;
    --token-accent: 215 203 177;
    --token-accent-soft: 215 203 177 / 0.12;
    --token-green: 34 197 94;
    --token-red: 248 113 113;
    --token-amber: 245 158 11;
    --token-radius-sm: 8px;
    --token-radius-md: 12px;
    --token-radius-lg: 16px;
    --token-radius-xl: 22px;
    --token-radius-full: 999px;
    --token-shadow-surface: 0 28px 72px rgba(0, 0, 0, 0.36);
    --token-shadow-panel: 0 8px 24px rgba(2, 6, 23, 0.32);
    --token-dur-fast: 80ms;
    --token-dur-base: 150ms;
    --token-dur-slow: 280ms;
    --token-ease-out: cubic-bezier(0.0, 0.0, 0.2, 1);
    --token-ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  }
}
```

Импортируй в `app.css` после `@import "tailwindcss"`:
```css
@import "./tokens.css";
```

#### ЧАСТЬ 3 — Шрифт Inter

```bash
npm install @fontsource-variable/inter
```

В `frontend/src/main.tsx` первой строкой:
```ts
import "@fontsource-variable/inter";
```

В `:root` в `app.css` — изменить font-family:
```css
font-family: "Inter Variable", "Inter", "Aptos", "Segoe UI Variable", "Segoe UI", sans-serif;
```

#### ЧАСТЬ 4 — shadcn/ui

```bash
npm install class-variance-authority clsx tailwind-merge lucide-react @radix-ui/react-slot
```

Создай `frontend/src/shared/lib/utils.ts`:
```ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Создай `frontend/src/shared/ui/primitives/Button.tsx` и `Badge.tsx` — см. оригинальную спецификацию в git history.

#### ЧАСТЬ 5 — Framer Motion

```bash
npm install framer-motion
```

Создай `frontend/src/styles/motion.ts` с пресетами: fadeIn, fadeInFast, scaleIn, slideInLeft, staggerContainer, staggerItem.

#### ЧАСТЬ 6 — UI Lab

Создай `frontend/src/features/ui-lab/UiLabPage.tsx`.
Добавь роут `/ui-lab` в `frontend/src/app/router.tsx`.
Добавь пункт "UI Lab" в nav в `AppShell.tsx`.

#### ЧАСТЬ 7 — Применить motion к HealthPage

Обернуть `app-route` в `<motion.div {...fadeIn}>`, карточки — в stagger.

#### ЧАСТЬ 8 — frontend/CLAUDE.md

Создать `frontend/CLAUDE.md` с правилами UI системы (токены, типографика, motion пресеты, запреты).

#### ЧАСТЬ 9 — Сборка и проверка

```bash
cd C:\ai\aiBotik\frontend
npm run typecheck
npm run build
npm run test
```

**Промт для запуска агента:**
```
Прочитай C:\ai\aiBotik\AGENTS_CONTEXT.md. Обнови статус UI-Foundation на 🔄.
После завершения запиши результат и статус ✅.
[Далее скопировать части 1-9 из ## Архив заданий]
```
