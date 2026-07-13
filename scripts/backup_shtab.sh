#!/usr/bin/env bash
set -euo pipefail

PYTHON="/home/claude/workspace/.google-auth-venv/bin/python"
"$PYTHON" - <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SOURCE = "1-ctgpF_yoyYBunJkkV1ZpPmp-NTFkvdBp5ep5kAGFeE"
FOLDER = "1fKmWcuIim9P2RDLv7hjoKbOBhzFgPSZd"
TOKEN = "/home/claude/.hermes/google_token.json"

today = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")
name = f"Бэкап 00_Штаб задач — {today}"
creds = Credentials.from_authorized_user_file(TOKEN)
drive = build("drive", "v3", credentials=creds, cache_discovery=False)

existing = drive.files().list(
    q=f"'{FOLDER}' in parents and name = '{name}' and trashed = false",
    fields="files(id,name)",
    pageSize=1,
).execute().get("files", [])
if existing:
    print(f"Бэкап уже есть: {existing[0]['name']}")
else:
    result = drive.files().copy(
        fileId=SOURCE,
        body={"name": name, "parents": [FOLDER]},
        fields="id,name,mimeType",
    ).execute()
    if result.get("mimeType") != "application/vnd.google-apps.spreadsheet":
        raise RuntimeError("Google Drive вернул не таблицу")
    print(f"Бэкап создан: {result['name']}")
PY
