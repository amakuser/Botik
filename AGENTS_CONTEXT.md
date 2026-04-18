# AGENTS_CONTEXT.md — Общая доска агентов

> **ПРОТОКОЛ (обязательно):**
> 1. Оркестратор ВСЕГДА пишет задачу сюда ДО запуска агентов
> 2. Каждый агент читает этот файл ПЕРВЫМ — до любых других действий
> 3. Агент пишет статус "🔄 в работе" сразу при старте
> 4. Агент пишет результат сюда ПЕРЕД тем как завершить работу
> 5. Оркестратор сбрасывает ## Задания и ## Статусы в начале новой задачи

---

## Текущая задача

**Задача:** Создать постоянную premium UI-систему для Botik (React/Tauri frontend).

**Контекст и цель:**
Botik — реальный торговый бот (Bybit), стек: React 19 + TypeScript + Vite + Tauri.
Фронтенд: `C:\ai\aiBotik\frontend\`
Задача — добавить solid foundation для UI работы: Tailwind v4, shadcn/ui, Framer Motion,
design tokens, типографику, motion-пресеты, UI Lab экран, применить к реальным экранам.

**Текущее состояние фронта:**
- Кастомный CSS (`frontend/src/styles/app.css`, 2000+ строк, BEM-style)
- CSS-переменные: `--surface-bg`, `--text-primary`, `--accent-strong` (#d7cbb1) и др. — уже есть
- Тёмная тема, glassmorphic поверхности, warm accent palette
- НЕТ Tailwind, shadcn/ui, Framer Motion, icon library
- Шрифт: системный "Aptos"/"Segoe UI Variable"
- 16 роутов, feature-based структура

**Важно:**
- НЕ ломать существующий CSS — он рабочий и хороший
- Tailwind v4 добавить РЯДОМ с app.css, не вместо него
- shadcn/ui использовать для НОВЫХ компонентов (кнопки, диалоги, badges и т.д.)
- Существующие BEM классы оставить работать как есть

---

## Задания

### Агент UI-Foundation ⬜ ожидает

**Прочитай этот файл первым. Обнови статус на 🔄. После завершения запиши результат и статус ✅.**

#### ЧАСТЬ 1 — Tailwind v4

Установи Tailwind v4 в `C:\ai\aiBotik\frontend\`:
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

Добавь в начало `frontend/src/styles/app.css` (ПЕРЕД остальным CSS):
```css
@import "tailwindcss";
```

#### ЧАСТЬ 2 — Design Tokens

Создай файл `frontend/src/styles/tokens.css` с полным набором токенов, совместимых с Tailwind v4 и существующим app.css:

```css
@layer base {
  :root {
    /* Surface */
    --token-bg-base: 5 7 11;           /* #05070b */
    --token-bg-surface: 14 18 24;      /* #0e1218 */
    --token-bg-panel: 18 22 28;        /* #12161c */
    --token-bg-subtle: 15 23 42;       /* #0f172a */

    /* Borders */
    --token-border-default: 201 209 220 / 0.12;
    --token-border-strong: 215 203 177 / 0.22;
    --token-border-accent: 215 203 177 / 0.38;

    /* Text */
    --token-text-primary: 237 241 247;   /* #edf1f7 */
    --token-text-secondary: 174 184 199; /* #aeb8c7 */
    --token-text-muted: 125 136 152;     /* #7d8898 */

    /* Accent (warm gold) */
    --token-accent: 215 203 177;          /* #d7cbb1 */
    --token-accent-soft: 215 203 177 / 0.12;

    /* Semantic */
    --token-green: 34 197 94;
    --token-red: 248 113 113;
    --token-amber: 245 158 11;

    /* Radius */
    --token-radius-sm: 8px;
    --token-radius-md: 12px;
    --token-radius-lg: 16px;
    --token-radius-xl: 22px;
    --token-radius-full: 999px;

    /* Shadow */
    --token-shadow-surface: 0 28px 72px rgba(0, 0, 0, 0.36);
    --token-shadow-panel: 0 8px 24px rgba(2, 6, 23, 0.32);

    /* Motion */
    --token-dur-fast: 80ms;
    --token-dur-base: 150ms;
    --token-dur-slow: 280ms;
    --token-ease-out: cubic-bezier(0.0, 0.0, 0.2, 1);
    --token-ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  }
}
```

Импортируй `tokens.css` в `app.css` сразу после `@import "tailwindcss"`:
```css
@import "./tokens.css";
```

#### ЧАСТЬ 3 — Шрифт Inter

Установи Inter variable font:
```bash
npm install @fontsource-variable/inter
```

Импортируй в `frontend/src/main.tsx` (САМОЙ ПЕРВОЙ строкой):
```ts
import "@fontsource-variable/inter";
```

Обнови `:root` в `app.css` — измени font-family:
```css
font-family: "Inter Variable", "Inter", "Aptos", "Segoe UI Variable", "Segoe UI", sans-serif;
```

#### ЧАСТЬ 4 — shadcn/ui

Установи shadcn/ui вручную (не через интерактивный CLI):

```bash
cd C:\ai\aiBotik\frontend
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

Создай `frontend/src/shared/ui/primitives/Button.tsx` — shadcn-style Button:
```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-full text-sm font-semibold transition-all duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "bg-gradient-to-b from-[#e4dbc9] to-[#b8aa8d] text-[#14161a] shadow-[inset_0_1px_0_rgba(255,255,255,0.28),0_12px_28px_rgba(0,0,0,0.18)] hover:-translate-y-px hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.34),0_16px_30px_rgba(0,0,0,0.22)]",
        secondary: "bg-[rgba(23,28,34,0.92)] border border-[rgba(201,209,220,0.16)] text-[#eef2f7] hover:-translate-y-px hover:border-[rgba(215,203,177,0.22)] hover:bg-[rgba(28,33,40,0.96)]",
        ghost: "text-[var(--text-secondary)] hover:bg-[rgba(215,203,177,0.08)] hover:text-[var(--text-primary)]",
        destructive: "bg-[rgba(248,113,113,0.16)] border border-[rgba(248,113,113,0.24)] text-[#fecaca] hover:bg-[rgba(248,113,113,0.22)]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        lg: "h-11 px-6 text-base",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
```

Создай `frontend/src/shared/ui/primitives/Badge.tsx`:
```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border transition-colors",
  {
    variants: {
      variant: {
        default: "bg-[rgba(215,203,177,0.1)] border-[rgba(215,203,177,0.18)] text-[#ece2cb]",
        success: "bg-[rgba(34,197,94,0.14)] border-[rgba(34,197,94,0.24)] text-[#86efac]",
        error:   "bg-[rgba(248,113,113,0.14)] border-[rgba(248,113,113,0.2)] text-[#fecaca]",
        warning: "bg-[rgba(217,119,6,0.16)] border-[rgba(245,158,11,0.18)] text-[#fde68a]",
        muted:   "bg-[rgba(15,23,42,0.82)] border-[rgba(148,163,184,0.14)] text-[#94a3b8]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
```

#### ЧАСТЬ 5 — Framer Motion + Motion Presets

```bash
npm install framer-motion
```

Создай `frontend/src/styles/motion.ts`:
```ts
export const motionTokens = {
  duration: {
    fast: 0.08,
    base: 0.15,
    slow: 0.28,
    page: 0.22,
  },
  ease: {
    out: [0.0, 0.0, 0.2, 1] as const,
    spring: { type: "spring" as const, stiffness: 400, damping: 30 },
    springBounce: { type: "spring" as const, stiffness: 600, damping: 35 },
  },
} as const;

export const fadeIn = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: motionTokens.duration.page, ease: motionTokens.ease.out },
};

export const fadeInFast = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: motionTokens.duration.base },
};

export const scaleIn = {
  initial: { opacity: 0, scale: 0.97 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.97 },
  transition: { duration: motionTokens.duration.base, ease: motionTokens.ease.out },
};

export const slideInLeft = {
  initial: { opacity: 0, x: -10 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -10 },
  transition: { duration: motionTokens.duration.slow, ease: motionTokens.ease.out },
};

export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.06 } },
};

export const staggerItem = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: motionTokens.duration.slow, ease: motionTokens.ease.out },
};
```

#### ЧАСТЬ 6 — UI Lab

Создай роут и страницу UI Lab:

Файл `frontend/src/features/ui-lab/UiLabPage.tsx`:
```tsx
import { motion } from "framer-motion";
import { fadeIn, staggerContainer, staggerItem } from "../../styles/motion";
import { Button } from "../../shared/ui/primitives/Button";
import { Badge } from "../../shared/ui/primitives/Badge";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";

function LabSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <SectionHeading title={title} />
      <div style={{ marginTop: 16 }}>{children}</div>
    </section>
  );
}

export function UiLabPage() {
  return (
    <AppShell>
      <motion.div className="app-route" {...fadeIn}>
        <PageIntro
          eyebrow="Разработка"
          title="UI Lab"
          description="Компоненты, токены, типографика, motion-пресеты — для визуального контроля качества."
        />

        {/* Buttons */}
        <LabSection title="Кнопки">
          <div className="toolbar-actions">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="primary" disabled>Disabled</Button>
          </div>
          <div className="toolbar-actions" style={{ marginTop: 12 }}>
            <Button variant="primary" size="sm">Small</Button>
            <Button variant="secondary" size="md">Medium</Button>
            <Button variant="secondary" size="lg">Large</Button>
          </div>
        </LabSection>

        {/* Badges */}
        <LabSection title="Badges">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Badge variant="default">Default</Badge>
            <Badge variant="success">Success</Badge>
            <Badge variant="error">Error</Badge>
            <Badge variant="warning">Warning</Badge>
            <Badge variant="muted">Muted</Badge>
          </div>
        </LabSection>

        {/* Typography */}
        <LabSection title="Типографика">
          <div style={{ display: "grid", gap: 12 }}>
            <h1 style={{ margin: 0 }}>Заголовок H1 — Botik Trading</h1>
            <h2 style={{ margin: 0 }}>Заголовок H2 — Состояние системы</h2>
            <h3 style={{ margin: 0 }}>Заголовок H3 — Фьючерсы</h3>
            <p style={{ margin: 0 }}>Body text — Основной текст для описаний и параграфов. Читаемый размер, правильный межстрочный интервал.</p>
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>Secondary text — вторичный текст, подписи, метаданные.</p>
            <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "0.82rem" }}>Muted / caption — очень мелкий вторичный текст.</p>
            <code style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: "0.88rem" }}>
              Monospace: 0.0042 BTC · $428,162.00 · BTCUSDT
            </code>
          </div>
        </LabSection>

        {/* Motion */}
        <LabSection title="Motion — Stagger">
          <motion.div
            className="home-metrics-grid"
            variants={staggerContainer}
            initial="initial"
            animate="animate"
          >
            {["Stagger 1", "Stagger 2", "Stagger 3", "Stagger 4"].map((label) => (
              <motion.article key={label} className="home-metric-card panel" variants={staggerItem}>
                <p className="home-metric-card__label">{label}</p>
                <strong className="home-metric-card__value">+12.34%</strong>
                <p className="home-metric-card__sub">sub text</p>
              </motion.article>
            ))}
          </motion.div>
        </LabSection>

        {/* Colors */}
        <LabSection title="Цветовая палитра">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 10 }}>
            {[
              { name: "accent", bg: "#d7cbb1", text: "#14161a" },
              { name: "bg-base", bg: "#05070b", text: "#edf1f7" },
              { name: "bg-surface", bg: "#0e1218", text: "#edf1f7" },
              { name: "bg-panel", bg: "#12161c", text: "#edf1f7" },
              { name: "green", bg: "rgba(34,197,94,0.18)", text: "#bbf7d0" },
              { name: "red", bg: "rgba(248,113,113,0.18)", text: "#fecaca" },
              { name: "amber", bg: "rgba(245,158,11,0.2)", text: "#fde68a" },
            ].map((token) => (
              <div
                key={token.name}
                style={{
                  background: token.bg,
                  color: token.text,
                  padding: "12px",
                  borderRadius: "var(--token-radius-md)",
                  border: "1px solid rgba(201,209,220,0.1)",
                  fontSize: "0.72rem",
                  fontWeight: 700,
                }}
              >
                {token.name}
              </div>
            ))}
          </div>
        </LabSection>

        {/* States */}
        <LabSection title="Состояния">
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <span className="runtime-state runtime-state--running">Running</span>
            <span className="runtime-state runtime-state--degraded">Degraded</span>
            <span className="runtime-state runtime-state--offline">Offline</span>
            <span className="status-chip is-completed">Completed</span>
            <span className="status-chip is-failed">Failed</span>
            <span className="status-chip">Default</span>
          </div>
        </LabSection>
      </motion.div>
    </AppShell>
  );
}
```

Добавь роут в `frontend/src/app/router.tsx`. Найди массив роутов и добавь:
```tsx
{ path: "/ui-lab", lazy: () => import("../features/ui-lab/UiLabPage").then(m => ({ Component: m.UiLabPage })) },
```

Добавь пункт навигации в `frontend/src/shared/ui/AppShell.tsx`. Найди nav группу с системными пунктами (Диагностика/Настройки) и добавь:
```tsx
{ to: "/ui-lab", label: "UI Lab" },
```

#### ЧАСТЬ 7 — Применить motion к HealthPage

В `frontend/src/features/health/HealthPage.tsx`:
1. Импортируй: `import { motion } from "framer-motion";`
2. Импортируй: `import { fadeIn, staggerContainer, staggerItem } from "../../styles/motion";`
3. Оберни возвращаемый `<div className="app-route home-layout">` в `<motion.div {...fadeIn} className="app-route home-layout">`
4. Оберни `<div className="home-metrics-grid">` в `<motion.div variants={staggerContainer} initial="initial" animate="animate" className="home-metrics-grid">`
5. Оберни каждый `<MetricCard>` в `<motion.div variants={staggerItem}>` (4 штуки)

#### ЧАСТЬ 8 — Создать/обновить frontend CLAUDE.md

Создай `frontend/CLAUDE.md`:

```markdown
# Frontend UI System — Botik

> Правила работы с UI для всех сессий агентов.

## Стек
- React 19 + TypeScript + Vite + Tauri
- Tailwind v4 (утилиты для новых компонентов)
- shadcn/ui-style primitives в `src/shared/ui/primitives/`
- Framer Motion для анимаций
- Inter Variable font

## Дизайн-токены
CSS-переменные в `src/styles/tokens.css`. Не использовать хардкод цветов/радиусов/теней.
Ключевые: `--token-accent` (#d7cbb1), `--token-bg-surface`, `--token-text-primary`.

## Типографика
- Основной шрифт: Inter Variable
- Числа/код: JetBrains Mono
- Шкала: 0.72rem caption → 0.82rem muted → 0.875rem secondary → 1rem base → 1.25rem subhead → 1.75rem value → 2rem+ heading

## Motion
- Пресеты в `src/styles/motion.ts` — ВСЕГДА использовать их, не придумывать новые значения
- Анимировать только значимые переходы: страницы (fadeIn), карточки при загрузке (staggerItem)
- Не анимировать каждый элемент
- Уважать prefers-reduced-motion
- Предпочитать transform + opacity

## CSS-архитектура
- Существующие BEM классы в `app.css` — оставлять как есть
- Новые компоненты: Tailwind utility классы через `cn()` из `src/shared/lib/utils.ts`
- Не смешивать Tailwind и BEM в одном элементе без необходимости

## Компоненты
- Примитивы (`Button`, `Badge`, etc.) — `src/shared/ui/primitives/`
- Переиспользуемые UI блоки — `src/shared/ui/`
- Страницы — `src/features/<name>/<Name>Page.tsx`

## Визуальный контроль
- После UI-изменений открыть `/ui-lab` для проверки компонентов
- Снять скриншот через `GET http://localhost:9989/screenshot` (dev tools)

## Запрещено
- Хардкод цветов (#hex, rgba) вне токенов — использовать CSS-переменные
- Произвольные анимации без motion.ts пресетов
- Произвольные тени без `--token-shadow-*`
- Добавлять Google Fonts через CDN в index.html
```

#### ЧАСТЬ 9 — Сборка и проверка

```bash
cd C:\ai\aiBotik\frontend
npm run typecheck
npm run build
npm run test
```

Запиши результаты в этот файл. Если тесты упали — исправь.

---

## Статусы

| Агент | Статус | Завершён |
|-------|--------|----------|
| переводчик | ✅ завершён | 2026-04-18 |
| UI-Foundation | ⬜ ожидает | — |
