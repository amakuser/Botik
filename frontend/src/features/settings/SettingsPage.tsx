import { useState } from "react";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { useSettingsModel } from "./hooks/useSettingsModel";
import { useSaveSettings } from "./hooks/useSaveSettings";
import { useTestBybit } from "./hooks/useTestBybit";
import type { BybitTestResult } from "../../shared/contracts";

interface FieldState {
  bybit_api_key: string;
  bybit_api_secret: string;
  bybit_mainnet_api_key: string;
  bybit_mainnet_api_secret: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  db_url: string;
}

const EMPTY: FieldState = {
  bybit_api_key: "",
  bybit_api_secret: "",
  bybit_mainnet_api_key: "",
  bybit_mainnet_api_secret: "",
  telegram_bot_token: "",
  telegram_chat_id: "",
  db_url: "",
};

function StatusDot({ present }: { present: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: present ? "#22c55e" : "rgba(201,209,220,0.28)",
        marginRight: 6,
        flexShrink: 0,
      }}
    />
  );
}

function FieldGroup({
  label,
  fieldKey,
  present,
  isSecret,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  fieldKey: keyof FieldState;
  present: boolean;
  isSecret: boolean;
  value: string;
  onChange: (key: keyof FieldState, val: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="settings-field">
      <label className="settings-field__label" htmlFor={`settings-${fieldKey}`}>
        <StatusDot present={present} />
        {label}
        {present && <span className="settings-field__badge">Настроено</span>}
      </label>
      <input
        id={`settings-${fieldKey}`}
        type={isSecret ? "password" : "text"}
        autoComplete="off"
        className="settings-field__input"
        placeholder={placeholder ?? (present ? "Оставьте пустым чтобы сохранить текущее" : "Не задано")}
        value={value}
        onChange={(e) => onChange(fieldKey, e.target.value)}
      />
    </div>
  );
}

function TestResultBadge({ result }: { result: BybitTestResult | undefined }) {
  if (!result) return null;
  const ok = result.state === "ok";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 12px",
        borderRadius: 999,
        fontSize: "0.85rem",
        background: ok ? "rgba(34,197,94,0.14)" : "rgba(248,113,113,0.14)",
        border: `1px solid ${ok ? "rgba(34,197,94,0.28)" : "rgba(248,113,113,0.28)"}`,
        color: ok ? "#86efac" : "#fca5a5",
      }}
    >
      {ok ? "✓" : "✗"} {result.detail ?? result.state}
      {result.latency_ms != null && ok ? ` · ${Math.round(result.latency_ms)}ms` : ""}
    </span>
  );
}

export function SettingsPage() {
  const snapshot = useSettingsModel();
  const saveSettings = useSaveSettings();
  const testBybit = useTestBybit();

  const [fields, setFields] = useState<FieldState>(EMPTY);
  const [saveMessage, setSaveMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [demoTestResult, setDemoTestResult] = useState<BybitTestResult | undefined>(undefined);
  const [mainnetTestResult, setMainnetTestResult] = useState<BybitTestResult | undefined>(undefined);

  const data = snapshot.data;
  const envFields = Object.fromEntries((data?.fields ?? []).map((f) => [f.key, f]));

  function handleChange(key: keyof FieldState, val: string) {
    setFields((prev) => ({ ...prev, [key]: val }));
  }

  function present(key: string) {
    return envFields[key]?.present ?? false;
  }

  async function handleSave() {
    setSaveMessage(null);
    const payload = {
      bybit_api_key: fields.bybit_api_key || null,
      bybit_api_secret: fields.bybit_api_secret || null,
      bybit_mainnet_api_key: fields.bybit_mainnet_api_key || null,
      bybit_mainnet_api_secret: fields.bybit_mainnet_api_secret || null,
      telegram_bot_token: fields.telegram_bot_token || null,
      telegram_chat_id: fields.telegram_chat_id || null,
      db_url: fields.db_url || null,
    };
    try {
      const result = await saveSettings.mutateAsync(payload);
      if (result.success) {
        setSaveMessage({ ok: true, text: `Saved ${(result.fields_written ?? []).length} field(s)` });
        setFields(EMPTY);
      } else {
        setSaveMessage({ ok: false, text: result.detail ?? "Save failed" });
      }
    } catch (err) {
      setSaveMessage({ ok: false, text: err instanceof Error ? err.message : "Save failed" });
    }
  }

  async function handleTestDemo() {
    setDemoTestResult(undefined);
    const key = fields.bybit_api_key || envFields["BYBIT_API_KEY"]?.value || "";
    const secret = fields.bybit_api_secret || envFields["BYBIT_API_SECRET"]?.value || "";
    if (!key || !secret || key.includes("***") || secret.includes("***")) {
      setDemoTestResult({ state: "error", detail: "Введите API ключ и секрет Demo для проверки", tested_at: new Date().toISOString() });
      return;
    }
    try {
      const result = await testBybit.mutateAsync({ host: "demo", api_key: key, api_secret: secret });
      setDemoTestResult(result);
    } catch (err) {
      setDemoTestResult({ state: "error", detail: err instanceof Error ? err.message : "Запрос не выполнен", tested_at: new Date().toISOString() });
    }
  }

  async function handleTestMainnet() {
    setMainnetTestResult(undefined);
    const key = fields.bybit_mainnet_api_key || envFields["BYBIT_MAINNET_API_KEY"]?.value || "";
    const secret = fields.bybit_mainnet_api_secret || envFields["BYBIT_MAINNET_API_SECRET"]?.value || "";
    if (!key || !secret || key.includes("***") || secret.includes("***")) {
      setMainnetTestResult({ state: "error", detail: "Введите API ключ и секрет MainNet для проверки", tested_at: new Date().toISOString() });
      return;
    }
    try {
      const result = await testBybit.mutateAsync({ host: "mainnet", api_key: key, api_secret: secret });
      setMainnetTestResult(result);
    } catch (err) {
      setMainnetTestResult({ state: "error", detail: err instanceof Error ? err.message : "Запрос не выполнен", tested_at: new Date().toISOString() });
    }
  }

  const configuredCount = (data?.fields ?? []).filter((f) => f.present ?? false).length;

  return (
    <AppShell>
      <div className="app-route settings-layout">
        <PageIntro
          eyebrow="Конфигурация"
          title="Настройки"
          description="API ключи, токен Telegram и база данных. Оставьте поле пустым чтобы сохранить текущее значение. Изменения записываются в .env файл."
          meta={
            <>
              <p className="status-caption">
                Источник: {data?.source_mode ?? "загрузка"}
              </p>
              <p className="status-caption">
                Настроено: {configuredCount} / {data?.fields?.length ?? "..."}
              </p>
              <p className="status-caption">
                .env: {data?.env_file_exists ? "присутствует" : "не найден"}
              </p>
            </>
          }
        />

        {snapshot.isError ? (
          <section className="panel">
            <p className="inline-error">Не удалось загрузить настройки.</p>
          </section>
        ) : null}

        {saveMessage ? (
          <section
            className="panel"
            style={{
              background: saveMessage.ok ? "rgba(34,197,94,0.08)" : "rgba(248,113,113,0.08)",
              border: `1px solid ${saveMessage.ok ? "rgba(34,197,94,0.22)" : "rgba(248,113,113,0.22)"}`,
            }}
          >
            <p style={{ margin: 0, color: saveMessage.ok ? "#86efac" : "#fca5a5" }}>
              {saveMessage.ok ? "✓" : "✗"} {saveMessage.text}
            </p>
          </section>
        ) : null}

        {/* Bybit Demo */}
        <section className="panel settings-panel">
          <div className="settings-panel__header">
            <SectionHeading title="Bybit Demo" description="API ключи для демо аккаунта (бумажная торговля)." />
            <div className="settings-panel__actions">
              <button type="button" className="button-secondary" onClick={() => void handleTestDemo()}>
                Проверить подключение
              </button>
              {demoTestResult ? <TestResultBadge result={demoTestResult} /> : null}
            </div>
          </div>
          <div className="settings-fields-grid">
            <FieldGroup label="API Ключ" fieldKey="bybit_api_key" isSecret present={present("BYBIT_API_KEY")} value={fields.bybit_api_key} onChange={handleChange} />
            <FieldGroup label="API Секрет" fieldKey="bybit_api_secret" isSecret present={present("BYBIT_API_SECRET")} value={fields.bybit_api_secret} onChange={handleChange} />
          </div>
        </section>

        {/* Bybit MainNet */}
        <section className="panel settings-panel">
          <div className="settings-panel__header">
            <SectionHeading title="Bybit MainNet" description="API ключи для реальной торговли — использовать осторожно." />
            <div className="settings-panel__actions">
              <button type="button" className="button-secondary" onClick={() => void handleTestMainnet()}>
                Проверить подключение
              </button>
              {mainnetTestResult ? <TestResultBadge result={mainnetTestResult} /> : null}
            </div>
          </div>
          <div className="settings-fields-grid">
            <FieldGroup label="API Ключ" fieldKey="bybit_mainnet_api_key" isSecret present={present("BYBIT_MAINNET_API_KEY")} value={fields.bybit_mainnet_api_key} onChange={handleChange} />
            <FieldGroup label="API Секрет" fieldKey="bybit_mainnet_api_secret" isSecret present={present("BYBIT_MAINNET_API_SECRET")} value={fields.bybit_mainnet_api_secret} onChange={handleChange} />
          </div>
        </section>

        {/* Telegram + DB */}
        <section className="panel settings-panel">
          <SectionHeading title="Telegram и база данных" description="Токен бота, Chat ID и строка подключения к базе данных." />
          <div className="settings-fields-grid">
            <FieldGroup label="Токен бота" fieldKey="telegram_bot_token" isSecret present={present("TELEGRAM_BOT_TOKEN")} value={fields.telegram_bot_token} onChange={handleChange} />
            <FieldGroup label="Chat ID" fieldKey="telegram_chat_id" isSecret={false} present={present("TELEGRAM_CHAT_ID")} value={fields.telegram_chat_id} onChange={handleChange} placeholder={present("TELEGRAM_CHAT_ID") ? "Оставьте пустым чтобы сохранить" : "например -1001234567890"} />
            <FieldGroup label="URL базы данных" fieldKey="db_url" isSecret={false} present={present("DB_URL")} value={fields.db_url} onChange={handleChange} placeholder={present("DB_URL") ? "Оставьте пустым чтобы сохранить" : "sqlite:///data/botik.db"} />
          </div>
        </section>

        {/* Save */}
        <section className="panel">
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              type="button"
              className="button-primary"
              disabled={saveSettings.isPending}
              onClick={() => void handleSave()}
            >
              {saveSettings.isPending ? "Сохранение…" : "Сохранить настройки"}
            </button>
            <p className="panel-muted" style={{ margin: 0 }}>
              Записываются только непустые поля. Секреты не возвращаются в ответе.
            </p>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
