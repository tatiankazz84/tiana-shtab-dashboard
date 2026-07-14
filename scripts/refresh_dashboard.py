#!/usr/bin/env python3
"""Build the public task HQ page from the live Google Sheet.

The sheet remains the source of truth. This renderer deliberately removes
financial and client-identifying wording before writing the public page.
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SHEET_ID = "1-ctgpF_yoyYBunJkkV1ZpPmp-NTFkvdBp5ep5kAGFeE"
ROOT = Path(__file__).resolve().parents[1]
GAPI = Path.home() / ".hermes/skills/productivity/google-workspace/scripts/google_api.py"
VENV_PYTHON = ROOT / ".venv-google/bin/python"

# Public names: the source sheet may hold private operating details.
PUBLIC_PARENT = {
    "Клиенты и оплаты": "Закрытый рабочий контур",
    "Зарплаты таргетологов": "Внутренний рабочий контур",
    "Ульям Медведь": "Клиентский контур",
}
PUBLIC_TASK = {
    "Создать закрытый реестр оплат клиентов": "Подготовить закрытый рабочий реестр",
    "Собрать даты ближайших оплат клиентов": "Сверить ближайшие плановые даты",
    "Настроить статусы оплат и просрочек": "Настроить рабочие статусы",
    "Настроить сводку по поступлениям": "Подготовить внутреннюю сводку",
    "Создать закрытый реестр выплат сотрудникам": "Подготовить закрытый рабочий реестр",
    "Собрать правила расчёта по каждому сотруднику": "Собрать правила внутреннего расчёта",
    "Собрать ближайшие даты выплат": "Сверить ближайшие плановые даты",
    "Настроить сверку начислено / проверено / оплачено": "Настроить внутреннюю сверку статусов",
    "Собрать налоговые и обязательные платежи": "Собрать регулярные обязательства",
    "Настроить плановые и фактические поступления": "Настроить внутреннее планирование",
    "Описать правило распределения денег": "Описать правило распределения ресурсов",
    "Настроить подсветку ближайших обязательств": "Настроить подсветку ближайших сроков",
    "Создать изолированное пространство клиента": "Подготовить изолированное рабочее пространство",
    "Проверить доступные источники клиентских материалов": "Проверить доступные рабочие источники",
    "Собрать правила запуска клиентского агента": "Собрать правила запуска рабочего контура",
}

# A new private label may appear in the live sheet before a specific mapping is
# added above. Keep the public page conservative in that case rather than
# letting finance terminology or a client name escape into the Mini App.
PRIVATE_TERMS = (
    "клиент", "оплат", "финанс", "зарплат", "выплат", "налог", "деньг",
    "поступлен", "начислен", "ульям медвед",
)


def get_range(a1: str) -> list[list[str]]:
    python = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    result = subprocess.run(
        [str(python), str(GAPI), "sheets", "get", SHEET_ID, a1],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def text(value: str) -> str:
    return html.escape(value, quote=True)


def safe_parent(name: str) -> str:
    mapped = PUBLIC_PARENT.get(name)
    if mapped:
        return mapped
    if any(term in name.casefold() for term in PRIVATE_TERMS):
        return "Закрытый рабочий контур"
    return name


def safe_task(name: str) -> str:
    mapped = PUBLIC_TASK.get(name)
    if mapped:
        return mapped
    if any(term in name.casefold() for term in PRIVATE_TERMS):
        return "Внутренняя задача закрытого контура"
    return name


def complete(row: dict) -> bool:
    return row["done"].strip() == "☑" or row["status"].strip().lower() == "готово"


def group_html(parent: dict, subtasks: list[dict]) -> str:
    done = sum(complete(item) for item in subtasks)
    items = []
    for item in subtasks:
        state = " done" if complete(item) else ""
        mark = "✓" if complete(item) else ""
        items.append(
            f'<li class="subtask{state}"><span class="mark">{mark}</span>'
            f'<span>{text(safe_task(item["task"]))}</span></li>'
        )
    return f'''<details class="task-group">
  <summary><span class="title">{text(safe_parent(parent["contour"]))}</span><span class="count">{done} из {len(subtasks)}</span></summary>
  <ul class="subtasks">{"".join(items)}</ul>
</details>'''


def main() -> None:
    tree_values = get_range("14_Дерево_задач!A1:N200")
    summary_values = get_range("15_Сводка_задач!A1:F30")

    rows: list[dict] = []
    for values in tree_values[5:]:
        values = values + [""] * (14 - len(values))
        if values[3] not in {"Задача", "Подзадача"}:
            continue
        rows.append({
            "id": values[0], "parent": values[1], "contour": values[2],
            "level": values[3], "task": values[4], "status": values[8],
            "done": values[9], "today": values[10], "comment": values[13],
        })

    parents = {row["id"]: row for row in rows if row["level"] == "Задача"}
    children: dict[str, list[dict]] = {key: [] for key in parents}
    for row in rows:
        if row["level"] == "Подзадача" and row["parent"] in children:
            children[row["parent"]].append(row)

    today_ids = []
    for row in rows:
        if row["level"] == "Подзадача" and row["today"].strip().lower() == "да" and row["parent"] not in today_ids:
            today_ids.append(row["parent"])
    today_ids = today_ids[:2]

    # The summary tab explicitly lists non-urgent contours. Keep this list as
    # the ordering source, then map it back to the task tree for subtasks.
    next_names = ""
    for row in summary_values:
        if row and row[0].strip() == "Следующие задачи" and len(row) > 1:
            next_names = row[1]
            break
    next_contours = [name.strip().casefold() for name in next_names.split(";") if name.strip()]
    next_ids = [
        parent_id for contour in next_contours
        for parent_id, parent in parents.items()
        if parent["contour"].casefold() == contour and parent_id not in today_ids
    ]

    metrics = {row[0].strip(): row[1].strip() for row in summary_values if len(row) > 1}
    total = int(metrics.get("Всего подзадач", "0") or 0)
    done = int(metrics.get("Готово", "0") or 0)
    progress = metrics.get("Прогресс", "0%").replace("%", "")
    try:
        percent = max(0, min(100, float(progress)))
    except ValueError:
        percent = round(done / total * 100) if total else 0

    render_marker = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    today_html = "".join(group_html(parents[parent_id], children[parent_id]) for parent_id in today_ids)
    next_html = "".join(group_html(parents[parent_id], children[parent_id]) for parent_id in next_ids)
    if not today_html:
        today_html = '<p class="empty">На сегодня в таблице нет открытых задач.</p>'
    if not next_html:
        next_html = '<p class="empty">Следующие несрочные задачи пока не выделены.</p>'

    page = f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="dashboard-render" content="{render_marker}">
  <title>Штаб задач</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@600;700;800;900&family=Quicksand:wght@700&display=swap');
    :root{{--ink:#24313a;--muted:#6d7b84;--mint:#55cfc2;--mint-dark:#278d89;--line:rgba(36,49,58,.1);--card:rgba(255,255,255,.9);--shadow:0 12px 28px rgba(52,89,100,.14)}}
    *{{box-sizing:border-box}} body{{margin:0;color:var(--ink);font-family:Nunito,system-ui,sans-serif;background:linear-gradient(180deg,#e7fbfb,#bfeef0);min-height:100vh}}
    main{{width:min(680px,100%);margin:auto;padding:16px 12px 28px}} .top{{display:flex;justify-content:space-between;align-items:center;font-size:13px;font-weight:900;color:#36777c;margin:0 4px 12px}} .date{{background:#fff;padding:7px 10px;border-radius:99px}}
    .hero{{padding:21px;border-radius:30px;background:linear-gradient(135deg,#dffaf7,#c8e6ff);box-shadow:var(--shadow);margin-bottom:12px}} h1,h2{{font-family:Quicksand,Nunito,sans-serif;margin:0;letter-spacing:-.045em}} h1{{font-size:34px;line-height:1}} .hero p{{margin:8px 0 0;font-weight:800;color:#46747a}}
    section{{margin-bottom:12px;padding:15px;border-radius:27px;background:var(--card);box-shadow:var(--shadow);border:1px solid rgba(255,255,255,.8)}} .head{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px}} h2{{font-size:23px}} .badge{{font-size:11px;font-weight:900;padding:7px 10px;border-radius:99px;background:#e7fbf8;color:#207c77}}
    .list{{display:grid;gap:9px}} details{{background:#fff;border:1px solid var(--line);border-radius:20px;padding:12px}} summary{{display:flex;align-items:center;gap:8px;cursor:pointer;list-style:none}} summary::-webkit-details-marker{{display:none}} summary::after{{content:'⌄';font-size:21px;color:var(--mint-dark);margin-left:4px}} details[open] summary::after{{transform:rotate(180deg)}} .title{{font-size:16px;font-weight:900;line-height:1.15;flex:1}} .count{{white-space:nowrap;font-size:12px;font-weight:900;padding:5px 8px;border-radius:99px;background:#eaf9fb;color:#27778a}} .subtasks{{margin:12px 0 0;padding:11px 0 0;border-top:1px solid var(--line);display:grid;gap:9px;list-style:none}} .subtask{{display:grid;grid-template-columns:21px 1fr;gap:8px;align-items:start;font-size:14px;font-weight:700;line-height:1.28;color:var(--muted)}} .mark{{width:20px;height:20px;border-radius:7px;border:2px solid #9bded9;background:#f1fffd;display:grid;place-items:center;color:#fff;font-weight:900}} .done{{opacity:.58}} .done .mark{{background:var(--mint);border-color:var(--mint-dark)}} .done span:last-child{{text-decoration:line-through}} .progress{{background:#fff;border:1px solid var(--line);border-radius:19px;padding:13px}} .progress-line{{display:flex;justify-content:space-between;gap:8px;font-size:16px;font-weight:900;margin-bottom:9px}} .bar{{height:10px;overflow:hidden;border-radius:99px;background:#e6eff1}} .bar i{{display:block;height:100%;width:{percent}%;background:linear-gradient(90deg,var(--mint),#ffd66b);border-radius:99px}} .empty{{margin:0;color:var(--muted);font-weight:700}}
  </style>
</head>
<body>
  <main>
    <div class="top"><span>Татьяна, штаб задач</span><span class="date" id="date"></span></div>
    <header class="hero"><h1>Штаб задач</h1><p>Фокус и следующий слой работы</p></header>
    <section><div class="head"><h2>Сегодня</h2><span class="badge" id="today-label"></span></div><div class="list">{today_html}</div></section>
    <section><div class="head"><h2>Следующие задачи</h2><span class="badge">не срочно</span></div><div class="list">{next_html}</div></section>
    <section><div class="head"><h2>Состояние</h2></div><div class="progress"><div class="progress-line"><span>{done} из {total} готово</span><span>{percent:g}%</span></div><div class="bar"><i></i></div></div></section>
  </main>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    window.Telegram?.WebApp?.ready(); window.Telegram?.WebApp?.expand();
    const date = new Intl.DateTimeFormat('ru-RU', {{timeZone:'Europe/Moscow', day:'numeric', month:'long'}}).format(new Date());
    document.getElementById('date').textContent = date; document.getElementById('today-label').textContent = date;
  </script>
</body>
</html>'''
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"Updated index.html: today={len(today_ids)}, next={len(next_ids)}, progress={done}/{total} ({percent:g}%)")


if __name__ == "__main__":
    main()
