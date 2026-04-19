# Frontend UI System — Botik

> Правила работы с UI для всех сессий агентов.

## Стек
- React 19 + TypeScript + Vite + Tauri
- Tailwind v4 (утилиты для новых компонентов, через `@tailwindcss/vite`)
- Primitives в `src/shared/ui/primitives/` (Button, Badge) с `cva` + `cn()`
- Framer Motion для анимаций
- Inter Variable font (`@fontsource-variable/inter`)

## Дизайн-токены
CSS-переменные в `src/styles/tokens.css`. **Не использовать хардкод цветов/радиусов/теней вне токенов.**
Ключевые токены:
- `--token-accent` → #d7cbb1 (warm gold)
- `--token-bg-surface`, `--token-bg-panel`, `--token-bg-subtle`
- `--token-text-primary`, `--token-text-secondary`, `--token-text-muted`
- `--token-radius-sm/md/lg/xl/full`
- `--token-shadow-surface`, `--token-shadow-panel`
- `--token-dur-fast/base/slow`, `--token-ease-out/spring`

## Типографика
- Основной шрифт: Inter Variable
- Числа / код: JetBrains Mono
- Шкала (приблизительно): 0.72rem caption → 0.82rem muted → 0.875rem label → 1rem body → 1.25rem subhead → 1.75rem value → 2rem+ heading
- font-variant-numeric: tabular-nums для финансовых чисел

## Motion
Пресеты в `src/styles/motion.ts` — **ВСЕГДА использовать их, не придумывать новые значения.**
- `fadeIn` — переход страниц (оборачивает `motion.div className="app-route"`)
- `staggerContainer` + `staggerItem` — карточки при загрузке данных
- `scaleIn` — всплывающие панели, диалоги
- `slideInLeft` — боковые панели, драверы
- Не анимировать каждый элемент, только значимые переходы
- Уважать `prefers-reduced-motion`
- Предпочитать `transform` + `opacity` (не `height`, не `width`)

## CSS-архитектура
- Существующие BEM классы в `app.css` — **оставлять как есть**
- Новые компоненты: Tailwind utility классы через `cn()` из `src/shared/lib/utils.ts`
- Не смешивать Tailwind и BEM в одном элементе без необходимости
- `@import "tailwindcss"` — первая строка в `app.css`

## Компоненты
- Примитивы (Button, Badge, ...) — `src/shared/ui/primitives/`
- Переиспользуемые UI блоки — `src/shared/ui/`
- Страницы — `src/features/<name>/<Name>Page.tsx`

## Визуальный контроль (обязательно после UI-изменений)
1. Открыть `/ui-lab` — проверить компоненты визуально
2. Снять скриншот: `GET http://localhost:9989/screenshot`
3. Проверить каждую затронутую страницу

## Visual Test Suite (`tests/visual/`)

Три слоя, независимые от друг друга:

| Слой | Файл | Что проверяет | Нужны baselines? |
|------|------|---------------|-----------------|
| Layout integrity | `layout.spec.ts` | overflow-x, zero-height, clipping — все 14 страниц | Нет — JS evaluate |
| Pixel regression | `regression.spec.ts` | Полностраничные PNG-diff для 6 ключевых страниц | Да — в `baselines/` |
| Helpers | `helpers.ts` | `waitForStableUI`, `checkLayoutIntegrity`, `getDynamicMasks` | — |

**Запуск:**
```powershell
# Все тесты (layout + regression)
.\scripts\test-visual.ps1

# Только layout (без baselines, быстро)
.\scripts\test-visual.ps1 -Layout

# Обновить baselines после намеренного UI-изменения
.\scripts\update-visual-baselines.ps1
```

**Правило:** После изменения CSS/компонентов → запустить `.\scripts\test-visual.ps1 -Layout`.  
После изменения layout/цветовой схемы → `.\scripts\update-visual-baselines.ps1` + commit baselines.

**Config:** `tests/visual/playwright.visual.config.ts` — `maxDiffPixelRatio: 0.05`, `threshold: 0.2`, viewport 1280×800, headless.  
**Baselines:** `tests/visual/baselines/*.png` — коммитить в git; платформо-независимы (генерируются headless Chromium).

## Запрещено
- Хардкод цветов (#hex, rgba()) вне `tokens.css` — использовать `var(--token-*)`
- Произвольные анимации без `motion.ts` пресетов
- Произвольные тени без `--token-shadow-*`
- CDN шрифты в `index.html`
- `any` типы в компонентах примитивов
