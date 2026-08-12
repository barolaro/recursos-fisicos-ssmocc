from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials


PROJECT_SHEET = "PROYECTOS"
USER_SHEET = "USUARIOS"
AUDIT_SHEET = "HISTORIAL"
CATALOG_SHEET = "CATALOGOS"

PROJECT_HEADERS = [
    "id", "bip", "name", "province", "commune", "facility_type", "category",
    "stage", "status", "funding", "progress", "owner_unit", "responsible",
    "start_date", "end_date", "contract_end", "guarantee_end", "current_tasks",
    "next_steps", "comments", "updated_at", "updated_by",
]
USER_HEADERS = ["email", "display_name", "role", "unit", "active"]
AUDIT_HEADERS = ["id", "project_id", "action", "detail", "changed_at", "changed_by"]
CATALOG_HEADERS = ["catalog", "value", "active"]


def configured() -> bool:
    try:
        return bool(st.secrets.get("GOOGLE_SHEET_ID")) and "gcp_service_account" in st.secrets
    except (FileNotFoundError, KeyError):
        return False


@st.cache_resource
def workbook():
    info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(credentials).open_by_key(st.secrets["GOOGLE_SHEET_ID"])


def _worksheet(title: str, headers: list[str]):
    book = workbook()
    try:
        sheet = book.worksheet(title)
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=title, rows=1000, cols=max(10, len(headers)))
    first = sheet.row_values(1)
    if not first:
        sheet.update(values=[headers], range_name="A1")
        sheet.freeze(rows=1)
    elif first != headers:
        raise ValueError(f"La hoja {title} no tiene la estructura esperada.")
    return sheet


def initialize() -> None:
    _worksheet(PROJECT_SHEET, PROJECT_HEADERS)
    _worksheet(USER_SHEET, USER_HEADERS)
    _worksheet(AUDIT_SHEET, AUDIT_HEADERS)
    _worksheet(CATALOG_SHEET, CATALOG_HEADERS)


def read_projects() -> pd.DataFrame:
    records = _worksheet(PROJECT_SHEET, PROJECT_HEADERS).get_all_records(
        expected_headers=PROJECT_HEADERS, numericise_ignore=[1]
    )
    frame = pd.DataFrame(records, columns=PROJECT_HEADERS)
    if frame.empty:
        return frame
    frame["progress"] = pd.to_numeric(frame["progress"], errors="coerce")
    for column in ["start_date", "end_date", "contract_end", "guarantee_end", "updated_at"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame.sort_values("name", key=lambda s: s.astype(str).str.lower()).reset_index(drop=True)


def _clean(value):
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def upsert_projects(frame: pd.DataFrame, actor: str) -> int:
    if frame.empty:
        return 0
    current = read_projects()
    incoming = frame.copy()
    now = datetime.now(timezone.utc).isoformat()
    incoming["updated_at"] = now
    incoming["updated_by"] = actor
    incoming = incoming.reindex(columns=PROJECT_HEADERS)
    if current.empty:
        merged = incoming
    else:
        merged = current.set_index("id")
        incoming = incoming.set_index("id")
        for project_id, row in incoming.iterrows():
            merged.loc[project_id, PROJECT_HEADERS[1:]] = row[PROJECT_HEADERS[1:]]
        merged = merged.reset_index()
    values = [PROJECT_HEADERS] + [[_clean(row.get(col)) for col in PROJECT_HEADERS] for _, row in merged.iterrows()]
    sheet = _worksheet(PROJECT_SHEET, PROJECT_HEADERS)
    sheet.clear()
    sheet.update(values=values, range_name="A1")
    sheet.freeze(rows=1)
    audit = [[str(uuid.uuid4()), str(project_id), "UPSERT", "Registro creado o actualizado", now, actor] for project_id in frame["id"]]
    _worksheet(AUDIT_SHEET, AUDIT_HEADERS).append_rows(audit, value_input_option="RAW")
    return len(frame)


def read_users() -> pd.DataFrame:
    records = _worksheet(USER_SHEET, USER_HEADERS).get_all_records(expected_headers=USER_HEADERS)
    return pd.DataFrame(records, columns=USER_HEADERS)


def replace_users(frame: pd.DataFrame, actor: str) -> int:
    users = frame.reindex(columns=USER_HEADERS).copy()
    users["email"] = users["email"].astype(str).str.strip().str.lower()
    users = users[users["email"].str.contains("@", na=False)].drop_duplicates("email")
    values = [USER_HEADERS] + [[_clean(row.get(col)) for col in USER_HEADERS] for _, row in users.iterrows()]
    sheet = _worksheet(USER_SHEET, USER_HEADERS)
    sheet.clear()
    sheet.update(values=values, range_name="A1")
    sheet.freeze(rows=1)
    _worksheet(AUDIT_SHEET, AUDIT_HEADERS).append_row(
        [str(uuid.uuid4()), "", "USUARIOS", f"Actualización de {len(users)} usuarios", datetime.now(timezone.utc).isoformat(), actor]
    )
    return len(users)


def get_user(email: str) -> dict | None:
    users = read_users()
    if users.empty:
        return None
    match = users[users["email"].astype(str).str.lower().str.strip() == email.lower().strip()]
    if match.empty:
        return None
    row = match.iloc[0].to_dict()
    row["active"] = str(row.get("active", "")).lower() in {"true", "verdadero", "1", "si", "sí", "x"}
    return row

