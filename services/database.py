from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text


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
      bip VARCHAR(80), name TEXT NOT NULL, province VARCHAR(100), commune VARCHAR(100),
      facility_type VARCHAR(100), category VARCHAR(150), stage VARCHAR(150), status VARCHAR(150),
      funding VARCHAR(150), progress FLOAT, owner_unit VARCHAR(120), responsible VARCHAR(200),
      start_date DATE, end_date DATE, contract_end DATE, guarantee_end DATE,
      current_tasks TEXT, next_steps TEXT, comments TEXT,
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


def init_db() -> None:
    with engine().begin() as conn:
        for statement in SCHEMA:
            conn.execute(text(statement))
    if not read_projects().empty:
        return
    now = datetime.now(timezone.utc)
    sample = pd.DataFrame([
        {"id": "demo-001", "bip": "40000001", "name": "Proyecto demostrativo de infraestructura", "province": "SANTIAGO", "commune": "SANTIAGO", "facility_type": "HOSPITAL", "category": "CONSERVACIÓN", "stage": "INVERSIÓN Ejecución", "status": "Construcción obra", "funding": "SECTORIAL SUB.31", "progress": 0.68, "owner_unit": "Obras", "responsible": "Equipo Obras", "start_date": None, "end_date": None, "contract_end": None, "guarantee_end": None, "current_tasks": "Seguimiento de avance", "next_steps": "Recepción provisoria", "comments": "Registro de demostración; puede eliminarse al cargar la base real.", "updated_at": now, "updated_by": "sistema"},
        {"id": "demo-002", "bip": "S/C", "name": "Adquisición demostrativa de equipamiento", "province": "TALAGANTE", "commune": "TALAGANTE", "facility_type": "HOSPITAL", "category": "ADQUISICIÓN DE E&E", "stage": "PRE-INVERSIÓN Perfil", "status": "Con pertinencia", "funding": "SECTORIAL SUB.29", "progress": 0.25, "owner_unit": "Inversiones", "responsible": "Equipo Inversiones", "start_date": None, "end_date": None, "contract_end": None, "guarantee_end": None, "current_tasks": "Preparación de antecedentes", "next_steps": "Solicitud de financiamiento", "comments": "Registro de demostración.", "updated_at": now, "updated_by": "sistema"},
    ])
    sample.to_sql("projects", engine(), if_exists="append", index=False)


def read_projects() -> pd.DataFrame:
    if not inspect(engine()).has_table("projects"):
        return pd.DataFrame()
    return pd.read_sql(text("SELECT * FROM projects ORDER BY name"), engine())


def upsert_projects(frame: pd.DataFrame, actor: str) -> int:
    if frame.empty:
        return 0
    frame = frame.copy()
    frame["updated_at"] = datetime.now(timezone.utc)
    frame["updated_by"] = actor
    cols = list(frame.columns)
    update_cols = [c for c in cols if c != "id"]
    dialect = engine().dialect.name
    with engine().begin() as conn:
        for record in frame.where(pd.notna(frame), None).to_dict("records"):
            if dialect == "postgresql":
                assignments = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                sql = f"INSERT INTO projects ({','.join(cols)}) VALUES ({','.join(':'+c for c in cols)}) ON CONFLICT (id) DO UPDATE SET {assignments}"
            else:
                assignments = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
                sql = f"INSERT INTO projects ({','.join(cols)}) VALUES ({','.join(':'+c for c in cols)}) ON CONFLICT(id) DO UPDATE SET {assignments}"
            conn.execute(text(sql), record)
            conn.execute(text("INSERT INTO audit_log (id, project_id, action, detail, changed_at, changed_by) VALUES (:id, :project_id, :action, :detail, :changed_at, :changed_by)"), {"id": str(uuid.uuid4()), "project_id": record["id"], "action": "UPSERT", "detail": "Registro creado o actualizado", "changed_at": datetime.now(timezone.utc), "changed_by": actor})
    return len(frame)


def get_user(email: str, admin_email: str) -> dict:
    email = email.lower().strip()
    if email == admin_email.lower().strip():
        return {"email": email, "display_name": "Administrador", "role": "Administrador", "unit": "Administración", "active": True}
    if inspect(engine()).has_table("users"):
        with engine().connect() as conn:
            row = conn.execute(text("SELECT email, display_name, role, unit, active FROM users WHERE LOWER(email)=:email"), {"email": email}).mappings().first()
            if row:
                return dict(row)
    return {"email": email, "display_name": email.split("@")[0], "role": "Consulta", "unit": "", "active": True}
