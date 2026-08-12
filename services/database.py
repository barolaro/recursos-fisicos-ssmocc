from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import bcrypt
from sqlalchemy import create_engine, inspect, text

from services import google_sheets


def backend_name() -> str:
    return "Google Sheets" if google_sheets.configured() else "Base SQL local"


def _database_url() -> str:
    try:
        return st.secrets["DATABASE_URL"]
    except (KeyError, FileNotFoundError):
        return os.getenv("DATABASE_URL", "sqlite:///recursos_fisicos.db")


@st.cache_resource
def engine():
    url = _database_url()
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS projects (
      id VARCHAR(36) PRIMARY KEY,
      grupo VARCHAR(8), bip VARCHAR(80), name TEXT NOT NULL, province VARCHAR(100), commune VARCHAR(100),
      facility_type VARCHAR(100), category VARCHAR(150), m2 VARCHAR(40), rate VARCHAR(20),
      stage VARCHAR(150), status VARCHAR(150), funding VARCHAR(150), progress FLOAT,
      owner_unit VARCHAR(120), responsible VARCHAR(200),
      start_date DATE, end_date DATE, contract_end DATE, guarantee_end DATE, guarantee_civil_end DATE,
      current_tasks TEXT, next_steps TEXT, commitment TEXT, comments TEXT,
      updated_at TIMESTAMP NOT NULL, updated_by VARCHAR(255)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
      email VARCHAR(255) PRIMARY KEY, display_name VARCHAR(255), role VARCHAR(40) NOT NULL,
      unit VARCHAR(120), active BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
      id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36), action VARCHAR(30) NOT NULL,
      detail TEXT, changed_at TIMESTAMP NOT NULL, changed_by VARCHAR(255) NOT NULL
    )
    """,
]

# Columnas agregadas después de la primera versión; se añaden en caliente a bases existentes.
_ADDED_COLUMNS = {
    "grupo": "VARCHAR(8)", "m2": "VARCHAR(40)", "rate": "VARCHAR(20)",
    "guarantee_civil_end": "DATE", "commitment": "TEXT",
}


def _ensure_columns() -> None:
    inspector = inspect(engine())
    if not inspector.has_table("projects"):
        return
    existing = {column["name"] for column in inspector.get_columns("projects")}
    with engine().begin() as conn:
        for column, sql_type in _ADDED_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {column} {sql_type}"))


def init_db() -> None:
    if google_sheets.configured():
        google_sheets.initialize()
        return
    with engine().begin() as conn:
        for statement in SCHEMA:
            conn.execute(text(statement))
    _ensure_columns()
    if not read_projects().empty:
        return
    now = datetime.now(timezone.utc)
    sample = pd.DataFrame([
        {"id": "demo-001", "grupo": "C", "bip": "40000001", "name": "Proyecto demostrativo de infraestructura", "province": "SANTIAGO", "commune": "SANTIAGO", "facility_type": "HOSPITAL", "category": "CONSERVACIÓN", "stage": "INVERSIÓN Ejecución", "status": "Construcción obra", "funding": "SECTORIAL SUB.31", "progress": 0.68, "owner_unit": "Obras", "responsible": "Equipo Obras", "start_date": None, "end_date": None, "contract_end": None, "guarantee_end": None, "current_tasks": "Seguimiento de avance", "next_steps": "Recepción provisoria", "comments": "Registro de demostración; puede eliminarse al cargar la base real.", "updated_at": now, "updated_by": "sistema"},
        {"id": "demo-002", "grupo": "D", "bip": "S/C", "name": "Adquisición demostrativa de equipamiento", "province": "TALAGANTE", "commune": "TALAGANTE", "facility_type": "HOSPITAL", "category": "ADQUISICIÓN DE E&E", "stage": "PRE-INVERSIÓN Perfil", "status": "Con pertinencia", "funding": "SECTORIAL SUB.29", "progress": 0.25, "owner_unit": "Inversiones", "responsible": "Equipo Inversiones", "start_date": None, "end_date": None, "contract_end": None, "guarantee_end": None, "current_tasks": "Preparación de antecedentes", "next_steps": "Solicitud de financiamiento", "comments": "Registro de demostración.", "updated_at": now, "updated_by": "sistema"},
    ])
    sample.to_sql("projects", engine(), if_exists="append", index=False)


def read_projects() -> pd.DataFrame:
    if google_sheets.configured():
        return google_sheets.read_projects()
    if not inspect(engine()).has_table("projects"):
        return pd.DataFrame()
    return pd.read_sql(text("SELECT * FROM projects ORDER BY name"), engine())


def _bind_value(value):
    """Convierte tipos de pandas/numpy a tipos nativos que acepta el driver SQL."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().replace(tzinfo=None)
    if hasattr(value, "item"):  # numpy int/float/bool escalares
        return value.item()
    return value


def upsert_projects(frame: pd.DataFrame, actor: str) -> int:
    if google_sheets.configured():
        return google_sheets.upsert_projects(frame, actor)
    if frame.empty:
        return 0
    frame = frame.copy()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    frame["updated_at"] = now
    frame["updated_by"] = actor
    cols = list(frame.columns)
    update_cols = [c for c in cols if c != "id"]
    dialect = engine().dialect.name
    with engine().begin() as conn:
        for raw in frame.where(pd.notna(frame), None).to_dict("records"):
            record = {k: _bind_value(v) for k, v in raw.items()}
            if dialect == "postgresql":
                assignments = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                sql = f"INSERT INTO projects ({','.join(cols)}) VALUES ({','.join(':'+c for c in cols)}) ON CONFLICT (id) DO UPDATE SET {assignments}"
            else:
                assignments = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
                sql = f"INSERT INTO projects ({','.join(cols)}) VALUES ({','.join(':'+c for c in cols)}) ON CONFLICT(id) DO UPDATE SET {assignments}"
            conn.execute(text(sql), record)
            conn.execute(text("INSERT INTO audit_log (id, project_id, action, detail, changed_at, changed_by) VALUES (:id, :project_id, :action, :detail, :changed_at, :changed_by)"), {"id": str(uuid.uuid4()), "project_id": record["id"], "action": "UPSERT", "detail": "Registro creado o actualizado", "changed_at": now, "changed_by": actor})
    return len(frame)


def get_user(email: str, admin_email: str) -> dict:
    email = email.lower().strip()
    if email == admin_email.lower().strip():
        return {"email": email, "display_name": "Administrador", "role": "Administrador", "unit": "Administración", "active": True}
    if google_sheets.configured():
        user = google_sheets.get_user(email)
        return user or {"email": email, "display_name": email.split("@")[0], "role": "Sin acceso", "unit": "", "active": False}
    if inspect(engine()).has_table("users"):
        with engine().connect() as conn:
            row = conn.execute(text("SELECT email, display_name, role, unit, active FROM users WHERE LOWER(email)=:email"), {"email": email}).mappings().first()
            if row:
                return dict(row)
    return {"email": email, "display_name": email.split("@")[0], "role": "Consulta", "unit": "", "active": True}


def authenticate_user(username: str, password: str) -> dict | None:
    username = username.strip().lower()
    admin_username = str(st.secrets.get("ADMIN_USERNAME", "admin")).strip().lower()
    admin_password = str(st.secrets.get("ADMIN_PASSWORD", ""))
    if username == admin_username and admin_password and password == admin_password:
        return {"username": username, "display_name": "Administrador", "role": "Administrador", "unit": "Administración", "active": True}
    if google_sheets.configured():
        return google_sheets.authenticate(username, password)
    return None


def read_users() -> pd.DataFrame:
    if google_sheets.configured():
        return google_sheets.read_users()
    if not inspect(engine()).has_table("users"):
        return pd.DataFrame(columns=["username", "display_name", "role", "unit", "active", "password_hash"])
    return pd.DataFrame(columns=["username", "display_name", "role", "unit", "active", "password_hash"])


def replace_users(frame: pd.DataFrame, actor: str) -> int:
    if google_sheets.configured():
        return google_sheets.replace_users(frame, actor)
    return 0


def delete_demo_projects() -> None:
    if google_sheets.configured():
        return
    with engine().begin() as conn:
        conn.execute(text("DELETE FROM projects WHERE id LIKE 'demo-%'"))
