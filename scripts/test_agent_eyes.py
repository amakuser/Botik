"""
Тест "агент глаза" — llama3.2-vision:11b как визуальный наблюдатель.
Проверяем: обнаружение ошибок, состояний, активной навигации, изменений.
"""
import urllib.request
import json
import base64
import time
import sys
from pathlib import Path

BASELINES = Path(__file__).parent.parent / "tests" / "visual" / "baselines"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "llama3.2-vision:11b"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def ask(question: str, image_path: str, system: str = None, max_tokens: int = 350) -> tuple[str, float]:
    img = encode_image(image_path)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": question, "images": [img]})

    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "num_predict": max_tokens}
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with opener.open(req, timeout=180) as resp:
        data = json.loads(resp.read())
    latency = time.time() - t0
    return data["message"]["content"].strip(), latency


def ask_json(question: str, image_path: str, schema_desc: str, max_tokens: int = 200) -> tuple[dict | None, float]:
    img = encode_image(image_path)
    system = f"You are a UI inspector. Respond ONLY with valid JSON. Schema: {schema_desc}"
    payload = json.dumps({
        "model": MODEL,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question, "images": [img]}
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": max_tokens}
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with opener.open(req, timeout=180) as resp:
        data = json.loads(resp.read())
    latency = time.time() - t0
    text = data["message"]["content"].strip()
    try:
        return json.loads(text), latency
    except json.JSONDecodeError:
        return None, latency


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def result_line(ok: bool, label: str, detail: str, latency: float):
    icon = "✅" if ok else "❌"
    print(f"{icon} {label} ({latency:.1f}s)")
    print(f"   → {detail}")


# ─────────────────────────────────────────────
# ТЕСТ 1: Обнаружение error banner
# ─────────────────────────────────────────────
separator("ТЕСТ 1: Обнаружение ошибки (error banner)")

print("Скриншот: state-runtime-error-banner.png")
answer, lat = ask(
    "Is there an error banner, warning, or alert visible in this screenshot? "
    "What color is it? What does it say? Be specific.",
    str(BASELINES / "state-runtime-error-banner.png"),
    max_tokens=300
)
print(f"Ответ ({lat:.1f}s):\n{answer}\n")

# сравниваем с нормальным состоянием
print("Скриншот: runtime.png (нормальное состояние)")
answer2, lat2 = ask(
    "Is there an error banner, warning, or alert visible in this screenshot? "
    "What color is it? What does it say? Be specific.",
    str(BASELINES / "runtime.png"),
    max_tokens=300
)
print(f"Ответ ({lat2:.1f}s):\n{answer2}\n")

# ─────────────────────────────────────────────
# ТЕСТ 2: Состояние рантайма (running vs offline)
# ─────────────────────────────────────────────
separator("ТЕСТ 2: Running vs Offline состояние карточки")

schema = '{"status": "running|stopped|unknown", "color": "string", "label_text": "string"}'

print("Скриншот: region-runtime-spot-running.png")
result, lat = ask_json(
    "What is the status of the Spot trading card? Is it running or stopped? What color indicator do you see?",
    str(BASELINES / "region-runtime-spot-running.png"),
    schema
)
result_line(
    result is not None and "running" in str(result.get("status", "")).lower(),
    "Spot RUNNING детект", str(result), lat
)

print()
print("Скриншот: region-runtime-spot-offline.png")
result2, lat2 = ask_json(
    "What is the status of the Spot trading card? Is it running or stopped? What color indicator do you see?",
    str(BASELINES / "region-runtime-spot-offline.png"),
    schema
)
result_line(
    result2 is not None and any(w in str(result2.get("status", "")).lower() for w in ["stop", "offline", "unknown"]),
    "Spot OFFLINE детект", str(result2), lat2
)

# ─────────────────────────────────────────────
# ТЕСТ 3: Активный пункт навигации
# ─────────────────────────────────────────────
separator("ТЕСТ 3: Активный пункт навигации")

print("Скриншот: sidebar-nav-spot-active.png")
nav_answer, lat = ask(
    "Look at the sidebar navigation menu. Which item is currently active/selected? "
    "How can you tell it's active (color, highlight, underline)?",
    str(BASELINES / "sidebar-nav-spot-active.png"),
    max_tokens=250
)
print(f"Ответ ({lat:.1f}s):\n{nav_answer}\n")

nav_ok = any(w in nav_answer.lower() for w in ["spot", "спот"])
result_line(nav_ok, "Детект активной вкладки Spot", nav_answer[:100] + "...", lat)

# ─────────────────────────────────────────────
# ТЕСТ 4: Telegram error banner
# ─────────────────────────────────────────────
separator("ТЕСТ 4: Telegram error banner")

print("Скриншот: state-telegram-error-banner.png")
tg_result, lat = ask_json(
    "Is there an error or warning banner visible? What does it say?",
    str(BASELINES / "state-telegram-error-banner.png"),
    '{"has_error": true|false, "error_text": "string", "banner_color": "string"}'
)
result_line(
    tg_result is not None and tg_result.get("has_error") is True,
    "Telegram error banner детект", str(tg_result), lat
)

# ─────────────────────────────────────────────
# ТЕСТ 5: Сравнение двух состояний (before/after)
# ─────────────────────────────────────────────
separator("ТЕСТ 5: Состояние runtime-card")

print("Скриншот: runtime-card-running-state.png")
running_answer, lat = ask(
    "Describe the state of the runtime card. Is anything running? "
    "What status indicators do you see? What colors?",
    str(BASELINES / "runtime-card-running-state.png"),
    max_tokens=300
)
print(f"Ответ ({lat:.1f}s):\n{running_answer}\n")

# ─────────────────────────────────────────────
# ИТОГ
# ─────────────────────────────────────────────
separator("ИТОГ")
print("Все тесты завершены.")
print("Вывод: можно ли использовать llama3.2-vision:11b как 'агент глаза'?")
print("Ключевые метрики: обнаружение ошибок, состояний, навигации.")
