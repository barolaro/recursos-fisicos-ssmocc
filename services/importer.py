from __future__ import annotations

import hashlib
import re
import unicodedata
from io import BytesIO

import pandas as pd


PROJECT_COLUMNS = ["id", "bip", "name", "province", "commune", "facility_type", "category", "stage", "status", "funding", "progress", "owner_unit", "responsible", "start_date", "end_date", "contract_end", "guarantee_end", "current_tasks", "next_steps", "comments"]


def _norm(value: object) -> str:
    value = "" if value is None else str(value)
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", value).strip().lower()


ALIASES = {
    "bip": ["cod bip", "cod. bip", "codigo bip", "bip"],
    "name": ["nombre del proyecto", "proyecto", "nombre"],
    "province": ["provincia"], "commune": ["comuna"],
    "facility_type": ["tipo de establecimiento", "establecimiento"],
    "category": ["categoria", "tipo"], "stage": ["etapa actual", "etapa"],
    "status": ["estado"], "funding": ["financiamiento"],
    "progress": ["% estado", "avance", "porcentaje de avance"],
    "owner_unit": ["encargado", "unidad"], "responsible": ["responsable"],
    "start_date": ["fecha inicio"], "end_date": ["fecha termino"],
    "contract_end": ["vigencia contrato convenio proyecto"],
    "guarantee_end": ["vigencia fiel cumplimiento correcta ejecucion"],
    "current_tasks": ["tareas en desarrollo", "planificacion"],
    "next_steps": ["siguientes etapas proyecto", "proxima etapa"],
    "comments": ["comentarios", "comentarios / 28.07.2026", "observaciones"],
}


def _find_header(raw: pd.DataFrame) -> int:
    for idx in range(min(12, len(raw))):
        cells = {_norm(v) for v in raw.iloc[idx].tolist()}
        score = sum(any(alias in cells for alias in aliases) for aliases in ALIASES.values())
        if score >= 3:
            return idx
    raise ValueError("No fue posible identificar la fila de encabezados.")


def parse_workbook(content: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    book = pd.ExcelFile(BytesIO(content))
    selected = sheet_name or next((s for s in book.sheet_names if _norm(s) in {"proy. inversion 2026", "proyectos", "proyectos inversiones"}), book.sheet_names[0])
    raw = pd.read_excel(book, sheet_name=selected, header=None)
    header = _find_header(raw)
    frame = pd.read_excel(book, sheet_name=selected, header=header)
    source = {_norm(c): c for c in frame.columns}
    result = pd.DataFrame()
    for target, names in ALIASES.items():
        match = next((source[n] for n in names if n in source), None)
        result[target] = frame[match] if match is not None else None
    result = result[result["name"].notna()].copy()
    result["name"] = result["name"].astype(str).str.strip()
    group_labels = r"(?i)(pre\s*-?\s*hospitalarios|atencion primaria de salud|hospitalarios|equipos(?: y equipamiento)?.*)"
    result = result[~result["name"].str.fullmatch(group_labels, na=False)]
    for col in ["start_date", "end_date", "contract_end", "guarantee_end"]:
        result[col] = pd.to_datetime(result[col], errors="coerce").dt.date
    result["progress"] = pd.to_numeric(result["progress"], errors="coerce")
    result["id"] = result.apply(lambda r: hashlib.sha256(f"{_norm(r['bip'])}|{_norm(r['name'])}".encode()).hexdigest()[:36], axis=1)
    return result.reindex(columns=PROJECT_COLUMNS)
