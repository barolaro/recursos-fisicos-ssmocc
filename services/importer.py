"""Importación de planillas institucionales SSMOC.

Reconoce automáticamente el tipo de cada hoja (Cartera de Inversión,
Planificación, Obras y Contratos, Convenio de Programación) y las normaliza
a un único esquema de proyectos que alimenta las tres pestañas del panel.

Soporta:
  * 00_MATRIZ_PROYECTOS_2026.xlsx  (multihoja: Inversión + Planificación + Convenio)
  * Planilla_Inversiones.xlsx      (una hoja de cartera con compromisos)
  * Planilla_Obras.xlsx            (contratos, vigencias y garantías)
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from io import BytesIO

import pandas as pd


# Esquema base de un proyecto (sin updated_at/updated_by, que agrega la capa de datos).
PROJECT_COLUMNS = [
    "id", "grupo", "bip", "name", "province", "commune", "facility_type", "category",
    "m2", "rate", "stage", "status", "funding", "progress", "owner_unit", "responsible",
    "start_date", "end_date", "contract_end", "guarantee_end", "guarantee_civil_end",
    "current_tasks", "next_steps", "commitment", "comments",
]

# Fechas que deben interpretarse como tales al persistir/leer.
DATE_COLUMNS = ["start_date", "end_date", "contract_end", "guarantee_end", "guarantee_civil_end"]


def _norm(value: object) -> str:
    value = "" if value is None else str(value)
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", value).strip().lower()


# --- Alias de columnas por tipo de planilla -------------------------------------------------

CARTERA_ALIASES = {
    "grupo": ["grupo"],
    "bip": ["cod bip", "cod. bip", "codigo bip", "bip"],
    "name": ["nombre del proyecto", "proyecto", "nombre", "iniciativa"],
    "province": ["provincia"],
    "commune": ["comuna"],
    "facility_type": ["tipo de establecimiento", "establecimiento"],
    "category": ["categoria"],
    "m2": ["m2", "mt2", "metros cuadrados", "superficie"],
    "rate": ["rate"],
    "stage": ["etapa actual", "etapa"],
    "status": ["estado"],
    "funding": ["financiamiento", "fuente de financiamiento", "fuente financiamiento"],
    "progress": ["% estado", "% avance", "avance", "porcentaje de avance"],
    "owner_unit": ["encargado", "unidad"],
    "commitment": ["compromiso octubre 2026", "compromiso a octubre 2026", "compromiso"],
    "comments": ["comentarios", "observaciones", "comentario"],
}

OBRAS_ALIASES = {
    "name": ["proyecto", "proyecto / contrato", "nombre del proyecto"],
    "facility_type": ["establecimiento"],
    "category": ["tipo"],
    "responsible": ["responsable"],
    "start_date": ["fecha inicio"],
    "contract_end": ["fecha termino"],
    "status": ["estado"],
    "guarantee_end": ["vigencia fiel cumplimiento", "vigencia fiel cumplimiento correcta ejecucion", "garantia fiel cumplimiento"],
    "guarantee_civil_end": ["vigencia responsabilidad civil", "vigencia responsabilidad", "garantia responsabilidad civil"],
    "current_tasks": ["tareas en desarrollo"],
    "next_steps": ["siguientes etapas proyecto", "siguientes etapas", "proxima etapa"],
}

CONVENIO_ALIASES = {
    "item": ["item", "n", "nro", "numero"],
    "name": ["proyecto", "nombre del proyecto"],
    "bip": ["codigo bip", "cod bip", "cod. bip", "bip"],
    "commitment": ["compromiso a octubre 2026", "compromiso octubre 2026", "compromiso"],
}

# Etiquetas de grupo (filas separadoras que no son proyectos).
_GROUP_LABEL = re.compile(
    r"(?i)^\s*(pre\s*-?\s*hospitalarios|atencion primaria(?: de salud)?|hospitalarios|"
    r"equipos(?: y equipamiento)?|cosam|otras iniciativas|otros proyectos|"
    r"proyectos en postulacion.*)\s*$"
)


def _match_column(source, aliases):
    """Devuelve la columna original cuyo encabezado normalizado calza con algún alias.

    Prioriza calce exacto; luego permite que el encabezado *comience con* el alias
    (tolera encabezados truncados o con sufijos, p. ej. 'VIGENCIA FIEL CUMPLIMIENTO ...')."""
    for alias in aliases:
        if alias in source:
            return source[alias]
    for alias in aliases:
        for norm_header, original in source.items():
            if norm_header.startswith(alias):
                return original
    return None


def _find_header(raw, alias_sets):
    for idx in range(min(15, len(raw))):
        cells = {_norm(v) for v in raw.iloc[idx].tolist() if v is not None}
        best = 0
        for aliases_map in alias_sets:
            score = sum(any(any(h.startswith(a) or h == a for h in cells) for a in aliases)
                        for aliases in aliases_map.values())
            best = max(best, score)
        if best >= 3:
            return idx
    raise ValueError("No fue posible identificar la fila de encabezados.")


def _classify(headers):
    has = lambda *opts: any(any(h.startswith(o) for h in headers) for o in opts)
    if has("responsable") and has("siguientes etapas", "tareas en desarrollo", "vigencia fiel", "dias restantes"):
        return "obras"
    if has("compromiso") and has("codigo bip", "cod bip", "cod. bip") and not has("provincia"):
        return "convenio"
    if has("nombre del proyecto", "proyecto") and has("provincia", "etapa actual", "etapa"):
        return "cartera"
    return "otro"


def _to_str(series):
    return series.map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v))
                      else str(v).replace("\n", " ").strip()).replace({"nan": ""})


def _clean_bip(value):
    text = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    return re.sub(r"\.0$", "", text)


def make_id(bip, name):
    return hashlib.sha256(f"{_norm(bip)}|{_norm(name)}".encode()).hexdigest()[:36]


def _apply_aliases(frame, aliases):
    source = {_norm(c): c for c in frame.columns}
    out = pd.DataFrame(index=frame.index)
    for target, names in aliases.items():
        col = _match_column(source, names)
        out[target] = frame[col] if col is not None else None
    return out


# --- Parsers por tipo -----------------------------------------------------------------------

def _parse_cartera(frame, source_unit):
    out = _apply_aliases(frame, CARTERA_ALIASES)
    out["name"] = _to_str(out["name"])
    out = out[out["name"].str.len() > 2]
    out = out[~out["name"].str.match(_GROUP_LABEL)]
    out["bip"] = out["bip"].map(_clean_bip)
    for col in ["grupo", "province", "commune", "facility_type", "category", "m2",
                "rate", "stage", "status", "funding", "owner_unit", "commitment", "comments"]:
        out[col] = _to_str(out[col])
    # El texto de ENCARGADO se conserva como responsable; la unidad se define por el
    # origen de la hoja para no contaminar la pestaña Obras (que solo lista contratos).
    out["responsible"] = out["owner_unit"]
    out["owner_unit"] = source_unit
    out["progress"] = out["progress"].map(_ratio)
    return out


def _parse_obras(frame):
    out = _apply_aliases(frame, OBRAS_ALIASES)
    out["name"] = _to_str(out["name"])
    out = out[out["name"].str.len() > 2]
    out = out[~out["name"].str.match(_GROUP_LABEL)]
    for col in ["facility_type", "category", "responsible", "status", "current_tasks", "next_steps"]:
        out[col] = _to_str(out[col])
    for col in ["start_date", "contract_end", "guarantee_end", "guarantee_civil_end"]:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.date
    out["owner_unit"] = "Obras"
    out["bip"] = ""
    return out


def _parse_convenio(frame):
    out = _apply_aliases(frame, CONVENIO_ALIASES)
    out["name"] = _to_str(out["name"])
    out = out[out["name"].str.len() > 2]
    out = out[~out["name"].str.match(_GROUP_LABEL)]
    out["bip"] = out["bip"].map(_clean_bip)
    out["commitment"] = _to_str(out["commitment"])
    return out[["name", "bip", "commitment"]]


def _resolve_unit(encargado, source_unit):
    tokens = {"obras": "Obras", "inversiones": "Inversiones", "inversion": "Inversiones",
              "planificacion": "Planificación", "planificación": "Planificación"}
    return tokens.get(_norm(encargado), source_unit)


def _ratio(value):
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return round(number / 100, 4) if number > 1 else round(float(number), 4)


def _unit_from_sheet(sheet):
    name = _norm(sheet)
    if "planific" in name:
        return "Planificación"
    if "obra" in name:
        return "Obras"
    return "Inversiones"


# --- Orquestador ----------------------------------------------------------------------------

def parse_workbook(content, sheet_name=None):
    book = pd.ExcelFile(BytesIO(content))
    sheets = [sheet_name] if sheet_name else book.sheet_names

    # 1) Clasifica cada hoja reconocible.
    recognized = []  # (sheet, kind, frame, source_unit)
    for sheet in sheets:
        raw = pd.read_excel(book, sheet_name=sheet, header=None)
        try:
            header = _find_header(raw, [CARTERA_ALIASES, OBRAS_ALIASES, CONVENIO_ALIASES])
        except ValueError:
            continue
        frame = pd.read_excel(book, sheet_name=sheet, header=header)
        kind = _classify({_norm(c) for c in frame.columns})
        if kind != "otro":
            recognized.append((sheet, kind, frame, _unit_from_sheet(sheet)))

    # La hoja PLANIFICACIÓN es una vista derivada de la de Inversión: si ambas están
    # presentes se omite para evitar proyectos duplicados.
    has_inversion = any(k == "cartera" and u == "Inversiones" for _, k, _, u in recognized)
    if has_inversion:
        recognized = [r for r in recognized if not (r[1] == "cartera" and r[3] == "Planificación")]

    project_frames = []
    convenio_frames = []
    for sheet, kind, frame, source_unit in recognized:
        if kind == "cartera":
            project_frames.append(_parse_cartera(frame, source_unit))
        elif kind == "obras":
            project_frames.append(_parse_obras(frame))
        elif kind == "convenio":
            convenio_frames.append(_parse_convenio(frame))

    if not project_frames and not convenio_frames:
        raise ValueError("La planilla no contiene hojas reconocibles de proyectos, obras o convenio.")

    projects = pd.concat(project_frames, ignore_index=True) if project_frames else pd.DataFrame(columns=["name", "bip"])
    projects = projects.reindex(columns=PROJECT_COLUMNS)

    # Adjunta los compromisos del Convenio de Programación por código BIP.
    if convenio_frames:
        convenio = pd.concat(convenio_frames, ignore_index=True)
        compromiso_by_bip = {b: c for b, c in zip(convenio["bip"], convenio["commitment"]) if b and c}
        if not projects.empty:
            has_bip = projects["bip"].fillna("").astype(str).str.len() > 0
            projects.loc[has_bip, "commitment"] = projects.loc[has_bip].apply(
                lambda r: compromiso_by_bip.get(str(r["bip"]), r.get("commitment") or ""), axis=1)
        matched = set(projects["bip"].dropna().astype(str))
        extra = convenio[~convenio["bip"].isin(matched) & (convenio["commitment"].str.len() > 0)]
        if not extra.empty:
            stubs = extra.assign(owner_unit="Convenio", grupo="").reindex(columns=PROJECT_COLUMNS)
            projects = pd.concat([projects, stubs], ignore_index=True)

    projects = projects[projects["name"].fillna("").astype(str).str.len() > 2].copy()
    projects["id"] = projects.apply(lambda r: make_id(r["bip"], r["name"]), axis=1)
    projects = projects.drop_duplicates(subset="id", keep="last").reset_index(drop=True)
    return projects.reindex(columns=PROJECT_COLUMNS)
