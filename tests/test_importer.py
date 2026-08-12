from io import BytesIO

import pandas as pd

from services.importer import make_id, parse_workbook


def _to_bytes(frame: pd.DataFrame, sheet: str) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, header=False, sheet_name=sheet)
    return buffer.getvalue()


def test_parse_cartera_headers_and_source_unit():
    source = pd.DataFrame([
        ["", "PROYECTOS EN POSTULACIÓN"],
        ["GRUPO", "PROVINCIA", "COMUNA", "TIPO DE ESTABLECIMIENTO", "NOMBRE DEL PROYECTO",
         "CÓD. BIP", "ETAPA ACTUAL", "ESTADO", "FINANCIAMIENTO", "ENCARGADO"],
        ["B", "SANTIAGO", "RENCA", "CESFAM", "Proyecto prueba", "4001",
         "INVERSIÓN Ejecución", "Construcción obra", "SUB.31", "Obras"],
    ])
    result = parse_workbook(_to_bytes(source, "PROY. INVERSIÓN 2026"))
    assert len(result) == 1
    row = result.iloc[0]
    assert row["name"] == "Proyecto prueba"
    assert row["grupo"] == "B"
    # La unidad se define por el origen (hoja de inversión), no por el texto ENCARGADO.
    assert row["owner_unit"] == "Inversiones"
    # El ENCARGADO original se conserva como responsable.
    assert row["responsible"] == "Obras"


def test_parse_obras_maps_contract_and_guarantees():
    source = pd.DataFrame([
        ["", "PROGRAMACION DE TAREAS"],
        ["N°", "Establecimiento", "Proyecto", "TIPO", "RESPONSABLE", "FECHA TERMINO",
         "ESTADO", "VIGENCIA FIEL CUMPLIMIENTO", "SIGUIENTES ETAPAS PROYECTO"],
        [1, "Hospital X", "Contrato obra X", "DISEÑO", "Juan Pérez", "2026-10-20",
         "Vigente", "2026-12-15", "Estado de pago N°3"],
    ])
    result = parse_workbook(_to_bytes(source, "PROYECTOS"))
    assert len(result) == 1
    row = result.iloc[0]
    assert row["owner_unit"] == "Obras"
    assert str(row["contract_end"]) == "2026-10-20"
    assert str(row["guarantee_end"]) == "2026-12-15"
    assert row["next_steps"] == "Estado de pago N°3"


def test_make_id_is_stable():
    assert make_id("4001", "Proyecto prueba") == make_id("4001", "Proyecto prueba")
    assert make_id("4001", "A") != make_id("4002", "A")
