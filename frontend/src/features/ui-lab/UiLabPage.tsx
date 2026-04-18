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
