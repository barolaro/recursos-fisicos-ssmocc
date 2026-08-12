from io import BytesIO

import pandas as pd

from services.importer import parse_workbook


def test_parse_matrix_headers():
    source = pd.DataFrame([
        ["", "PROYECTOS"],
        ["PROVINCIA", "COMUNA", "TIPO DE ESTABLECIMIENTO", "NOMBRE DEL PROYECTO", "CÓD. BIP", "ETAPA ACTUAL", "ESTADO", "FINANCIAMIENTO", "ENCARGADO"],
        ["SANTIAGO", "RENCA", "CESFAM", "Proyecto prueba", "4001", "INVERSIÓN Ejecución", "Construcción obra", "SUB.31", "Obras"],
    ])
    content = BytesIO()
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        source.to_excel(writer, index=False, header=False, sheet_name="PROY. INVERSIÓN 2026")
    result = parse_workbook(content.getvalue())
    assert len(result) == 1
    assert result.iloc[0]["name"] == "Proyecto prueba"
    assert result.iloc[0]["owner_unit"] == "Obras"
