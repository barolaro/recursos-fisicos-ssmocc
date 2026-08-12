from __future__ import annotations

import json
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from services import google_sheets
from services.database import (
    authenticate_user, backend_name, delete_demo_projects, init_db, read_projects,
    read_users, replace_users, upsert_projects,
)
from services.importer import PROJECT_COLUMNS, make_id, parse_workbook


st.set_page_config(page_title="Recursos Físicos SSMOC", page_icon="🏥", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container{padding-top:1.5rem;max-width:1500px}.hero{padding:1.4rem 1.6rem;border-radius:16px;color:white;background:linear-gradient(120deg,#082349,#0C4C97 60%,#1E6FBF 130%);border-left:6px solid #DA2A2E;margin-bottom:1rem;box-shadow:0 12px 30px rgba(8,35,73,.18)}.hero h1{margin:0;font-size:2rem}.hero p{margin:.35rem 0 0;opacity:.9}.stMetric{background:white;border:1px solid #e5e7eb;border-top:3px solid #1E6FBF;padding:1rem;border-radius:12px}.badge{display:inline-block;padding:.2rem .65rem;border-radius:99px;background:#E9F1FA;color:#0C2E5E;font-weight:700;font-size:.78rem}
[data-testid="stSidebar"], [data-testid="collapsedControl"]{display:none!important}
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer{display:none!important}
[data-testid="stAppViewContainer"] > .main{margin-left:0!important}
.block-container{max-width:1660px;padding-left:1rem;padding-right:1rem}
.login-brand{text-align:center;padding:1rem .5rem .25rem}.login-brand img{width:150px;max-width:50%;border-radius:6px}.login-brand .eyebrow{font-size:.72rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#1E6FBF;margin:.75rem 0 .35rem}.login-brand h1{font-size:1.65rem;line-height:1.15;color:#082349;margin:0}.login-brand p{color:#687386;margin:.55rem 0}.login-foot{text-align:center;color:#7A8699;font-size:.72rem;padding:.4rem 0 0}
</style>
""", unsafe_allow_html=True)


def secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets[name])
    except (KeyError, FileNotFoundError):
        return default


def days_status(value) -> str:
    if value is None or pd.isna(value):
        return "Sin fecha"
    remaining = (pd.to_datetime(value).date() - date.today()).days
    if remaining < 0:
        return "Vencido"
    if remaining <= 30:
        return "Por vencer"
    return "Vigente"


MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
GRUPO_POR_UNIDAD = {"Obras": "B", "Inversiones": "D", "Planificación": "F", "Convenio": "F"}


def _isnull(value) -> bool:
    try:
        return value is None or pd.isna(value)
    except (TypeError, ValueError):
        return False


def _cell(row, key, default=""):
    value = row.get(key, default)
    return default if _isnull(value) else value


def _iso(value) -> str:
    if _isnull(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.date().isoformat()


def html_payload(frame: pd.DataFrame) -> dict:
    projects, works, convenio = [], [], []
    for _, row in frame.iterrows():
        unit = str(_cell(row, "owner_unit"))
        grupo = str(_cell(row, "grupo")).strip().upper() or GRUPO_POR_UNIDAD.get(unit, "G")
        commitment = str(_cell(row, "commitment")).strip()
        if unit != "Convenio":
            projects.append({
                "grupo": grupo, "prov": str(_cell(row, "province")), "comuna": str(_cell(row, "commune")),
                "tipo": str(_cell(row, "facility_type")), "nombre": str(_cell(row, "name")),
                "m2": str(_cell(row, "m2")), "cat": str(_cell(row, "category")), "bip": str(_cell(row, "bip")),
                "etapa": str(_cell(row, "stage")), "rate": str(_cell(row, "rate")), "estado": str(_cell(row, "status")),
                "fin": str(_cell(row, "funding")), "coment": str(_cell(row, "comments")),
                "enc": str(_cell(row, "responsible")) or unit,
            })
        if unit == "Obras":
            term = _iso(_cell(row, "contract_end", None))
            days = "" if not term else str((pd.to_datetime(term).date() - date.today()).days)
            works.append({
                "est": str(_cell(row, "facility_type")), "proy": str(_cell(row, "name")),
                "resp": str(_cell(row, "responsible")), "term": term, "dias": days,
                "estado": str(_cell(row, "status")),
                "gfc": _iso(_cell(row, "guarantee_end", None)) or "N/A",
                "grc": _iso(_cell(row, "guarantee_civil_end", None)) or "N/A",
                "sigetapa": str(_cell(row, "next_steps")),
            })
        if commitment:
            convenio.append({
                "item": str(len(convenio) + 1), "proy": str(_cell(row, "name")),
                "bip": str(_cell(row, "bip")), "compromiso": commitment,
            })
    now = datetime.now()
    return {
        "projects": projects, "obras": works, "convenio": convenio,
        "grupo_lbl": {"A": "Pre-Hospitalarios", "B": "Atención Primaria", "C": "Hospitalarios", "D": "Equipos y Equipamiento", "E": "COSAM", "F": "Otras Iniciativas", "G": "Otros Proyectos"},
        "gen": f"{now.day} de {MESES_ES[now.month]} de {now.year}",
    }


def render_html_dashboard(frame: pd.DataFrame) -> bool:
    template_path = Path(__file__).resolve().parent / "assets" / "panel_template.html"
    if not template_path.is_file():
        st.warning("El panel visual está actualizándose. Mientras tanto, puede utilizar el Resumen ejecutivo.")
        return False
    template = template_path.read_text(encoding="utf-8")
    base_url = "https://recursos-fisicos-ssmocc.streamlit.app/"
    rendered = template.replace("__DASHBOARD_DATA__", json.dumps(html_payload(frame), ensure_ascii=False, default=str))
    rendered = rendered.replace("__APP_BASE_URL__", base_url)
    components.html(rendered, height=1450, scrolling=True)
    return True


def model_workbook(kind: str) -> bytes:
    """Genera plantillas compatibles con el importador, listas para descargar."""
    cartera_columns = [
        "GRUPO", "PROVINCIA", "COMUNA", "TIPO DE ESTABLECIMIENTO",
        "NOMBRE DEL PROYECTO", "CÓD. BIP", "CATEGORÍA", "M2", "RATE",
        "ETAPA ACTUAL", "ESTADO", "FINANCIAMIENTO", "% AVANCE", "ENCARGADO",
        "COMPROMISO OCTUBRE 2026", "COMENTARIOS",
    ]
    obras_columns = [
        "ESTABLECIMIENTO", "PROYECTO", "TIPO", "RESPONSABLE", "FECHA INICIO",
        "FECHA TERMINO", "ESTADO", "VIGENCIA FIEL CUMPLIMIENTO",
        "VIGENCIA RESPONSABILIDAD CIVIL", "TAREAS EN DESARROLLO",
        "SIGUIENTES ETAPAS PROYECTO",
    ]
    convenio_columns = ["ITEM", "PROYECTO", "CÓDIGO BIP", "COMPROMISO A OCTUBRE 2026"]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if kind in {"matriz", "inversiones"}:
            pd.DataFrame(columns=cartera_columns).to_excel(
                writer, sheet_name="PROY. INVERSIÓN 2026" if kind == "matriz" else "INVERSIONES",
                index=False,
            )
        if kind == "matriz":
            pd.DataFrame(columns=cartera_columns).to_excel(writer, sheet_name="PLANIFICACIÓN", index=False)
            pd.DataFrame(columns=obras_columns).to_excel(writer, sheet_name="OBRAS Y CONTRATOS", index=False)
            pd.DataFrame(columns=convenio_columns).to_excel(writer, sheet_name="CONVENIO", index=False)
        elif kind == "obras":
            pd.DataFrame(columns=obras_columns).to_excel(writer, sheet_name="PROYECTOS", index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", fgColor="0C4C97")
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = min(
                    42, max(14, len(str(column[0].value or "")) + 3)
                )
    return output.getvalue()


init_db()
if str(st.query_params.get("logout", "")) == "1":
    st.session_state.pop("auth_user", None)
    st.query_params.clear()
    st.rerun()

if "auth_user" not in st.session_state:
    st.markdown("<style>.block-container{max-width:100%!important;padding:4vh 1rem!important;background:linear-gradient(135deg,#F4F7FB,#E9F1FA);min-height:100vh}</style>", unsafe_allow_html=True)
    _, login_col, _ = st.columns([1, 1.15, 1])
    with login_col:
        with st.container(border=True):
            st.markdown('''<div class="login-brand">
              <img src="https://gestordocumentalhsjd.ceropapel.cl/archivos/publico//logos/logo3.jpg" alt="Servicio de Salud Metropolitano Occidente">
              <div class="eyebrow">Servicio de Salud Metropolitano Occidente</div>
              <h1>Panel de Recursos Físicos</h1>
              <p>Departamento de Planificación · Acceso protegido</p>
            </div>''', unsafe_allow_html=True)
            with st.form("login", clear_on_submit=False):
                username = st.text_input("Usuario", placeholder="Ingrese su usuario").strip().lower()
                password = st.text_input("Contraseña", type="password", placeholder="Ingrese su contraseña")
                submitted = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
            st.markdown('<div class="login-foot">Sistema autogestionado · Las credenciales se validan de forma segura en el servidor.</div>', unsafe_allow_html=True)
    if submitted:
        authenticated = authenticate_user(username, password)
        if authenticated:
            st.session_state.auth_user = authenticated
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
    st.stop()
user = st.session_state.auth_user
email = str(user.get("username", ""))
display_name = str(user.get("display_name", email))
requested_view = str(st.query_params.get("view", "panel")).lower()

if requested_view == "panel":
    st.markdown("<style>.block-container{max-width:100%!important;padding:0!important}iframe{display:block;width:100%!important;border:0!important}</style>", unsafe_allow_html=True)
else:
    st.markdown('<div class="hero"><h1>Gestión de Recursos Físicos</h1><p>Administración, carga y actualización de información · SSMOC</p></div>', unsafe_allow_html=True)
    nav_a, nav_b, nav_c = st.columns(3)
    nav_a.link_button("📊 Panel", "?view=panel", use_container_width=True)
    nav_b.link_button("📤 Carga masiva", "?view=administracion", use_container_width=True)
    nav_c.link_button("✍️ Ingreso manual", "?view=nuevo", use_container_width=True)
    st.link_button("Cerrar sesión", "?logout=1")

with st.sidebar:
    st.markdown("### Sesión")
    st.write(display_name)
    st.markdown(f'<span class="badge">{user["role"]}</span>', unsafe_allow_html=True)
    st.caption(email)
    if user["role"] != "Administrador" and user.get("unit"):
        st.caption(f'Unidad: {user["unit"]}')
    section = st.radio("Navegación", ["Panel visual HTML", "Resumen ejecutivo", "Cartera de proyectos", "Actualizar proyecto", "Administración"] if user["role"] == "Administrador" else ["Panel visual HTML", "Resumen ejecutivo", "Cartera de proyectos", "Actualizar proyecto"] if user["role"] not in {"Dirección", "Consulta"} else ["Panel visual HTML", "Resumen ejecutivo", "Cartera de proyectos"])

# La interfaz pública abre directamente el panel HTML. El administrador puede
# abrir temporalmente una vista de gestión mediante ?view=administracion.
views = {
    "panel": "Panel visual HTML", "resumen": "Resumen ejecutivo",
    "cartera": "Cartera de proyectos", "actualizar": "Actualizar proyecto",
    "nuevo": "Nuevo proyecto", "administracion": "Administración",
}
allowed_by_role = {
    "Administrador": set(views),
    "Obras": {"panel", "cartera", "actualizar", "nuevo"},
    "Inversiones": {"panel", "cartera", "actualizar", "nuevo"},
    "Planificación": {"panel", "cartera", "actualizar", "nuevo"},
    "Dirección": {"panel", "resumen", "cartera"},
    "Consulta": {"panel", "cartera"},
}
allowed = allowed_by_role.get(str(user["role"]), {"panel"})
section = views.get(requested_view, "Panel visual HTML") if requested_view in allowed else "Panel visual HTML"

data = read_projects()
if user["role"] not in {"Administrador", "Dirección", "Consulta"} and user.get("unit"):
    data = data[data["owner_unit"].fillna("").str.lower() == user["unit"].lower()]

if section == "Panel visual HTML":
    render_html_dashboard(data)

elif section == "Resumen ejecutivo":
    st.subheader("Resumen ejecutivo")
    contracts = data["contract_end"].apply(days_status) if not data.empty else pd.Series(dtype=str)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proyectos", len(data))
    c2.metric("En ejecución", int(data["stage"].fillna("").str.contains("Ejecución", case=False).sum()) if not data.empty else 0)
    c3.metric("Por vencer", int((contracts == "Por vencer").sum()))
    c4.metric("Vencidos", int((contracts == "Vencido").sum()))
    left, right = st.columns(2)
    with left:
        if not data.empty:
            counts = data["status"].fillna("Sin estado").value_counts().head(10).rename_axis("Estado").reset_index(name="Proyectos")
            st.plotly_chart(px.bar(counts, x="Proyectos", y="Estado", orientation="h", color="Proyectos", color_continuous_scale="Blues"), use_container_width=True)
    with right:
        if not data.empty:
            units = data["owner_unit"].fillna("Sin unidad").value_counts().rename_axis("Unidad").reset_index(name="Proyectos")
            st.plotly_chart(px.pie(units, names="Unidad", values="Proyectos", hole=.55), use_container_width=True)
    st.subheader("Acciones prioritarias")
    priority = data.copy()
    priority["Alerta contrato"] = priority["contract_end"].apply(days_status)
    priority = priority[priority["Alerta contrato"].isin(["Vencido", "Por vencer"])]
    st.dataframe(priority[["name", "responsible", "contract_end", "Alerta contrato"]], hide_index=True, use_container_width=True)

elif section == "Cartera de proyectos":
    st.subheader("Cartera de proyectos")
    a, b, c = st.columns(3)
    province = a.multiselect("Provincia", sorted(data["province"].dropna().unique()))
    unit = b.multiselect("Unidad", sorted(data["owner_unit"].dropna().unique()))
    search = c.text_input("Buscar proyecto o BIP")
    view = data.copy()
    if province: view = view[view["province"].isin(province)]
    if unit: view = view[view["owner_unit"].isin(unit)]
    if search: view = view[view["name"].fillna("").str.contains(search, case=False) | view["bip"].fillna("").str.contains(search, case=False)]
    st.dataframe(view[["bip", "name", "commune", "stage", "status", "progress", "owner_unit", "responsible", "updated_at"]], hide_index=True, use_container_width=True, column_config={"progress": st.column_config.ProgressColumn("Avance", min_value=0, max_value=1, format="percent")})
    st.download_button("Descargar cartera filtrada", view.to_csv(index=False).encode("utf-8-sig"), "cartera_ssmoc.csv", "text/csv")

elif section == "Actualizar proyecto":
    st.subheader("Actualizar proyecto")
    if data.empty:
        st.info("No existen proyectos asignados.")
    else:
        labels = {f'{r["bip"] or "S/C"} · {r["name"]}': r["id"] for _, r in data.iterrows()}
        selected = st.selectbox("Proyecto", list(labels))
        row = data[data["id"] == labels[selected]].iloc[0].to_dict()
        with st.form("edit_project"):
            col1, col2 = st.columns(2)
            status = col1.text_input("Estado", row.get("status") or "")
            stage = col2.text_input("Etapa", row.get("stage") or "")
            progress = st.slider("Avance", 0, 100, int(float(row.get("progress") or 0) * 100)) / 100
            responsible = st.text_input("Responsable", row.get("responsible") or "")
            current_tasks = st.text_area("Tareas en desarrollo", row.get("current_tasks") or "")
            next_steps = st.text_area("Próximas etapas", row.get("next_steps") or "")
            comments = st.text_area("Comentario ejecutivo", row.get("comments") or "")
            if st.form_submit_button("Guardar actualización", type="primary"):
                row.update({"status": status, "stage": stage, "progress": progress, "responsible": responsible, "current_tasks": current_tasks, "next_steps": next_steps, "comments": comments})
                frame = pd.DataFrame([{c: row.get(c) for c in PROJECT_COLUMNS}])
                upsert_projects(frame, email)
                st.success("Proyecto actualizado y registrado en el historial.")
                st.cache_data.clear()

elif section == "Nuevo proyecto":
    st.subheader("Nuevo proyecto (carga manual)")
    st.caption("Registre un proyecto individual. Si el código BIP y el nombre coinciden con uno existente, se actualizará.")
    unidades = ["Inversiones", "Obras", "Planificación"]
    grupos = ["", "A", "B", "C", "D", "E", "F", "G"]
    default_unit = user.get("unit") if user.get("unit") in unidades else "Inversiones"
    with st.form("new_project", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("Nombre del proyecto *")
        bip = col2.text_input("Código BIP", "S/C")
        owner_unit = col3.selectbox("Unidad responsable", unidades, index=unidades.index(default_unit))
        col4, col5, col6 = st.columns(3)
        grupo = col4.selectbox("Grupo (A–G)", grupos)
        province = col5.text_input("Provincia")
        commune = col6.text_input("Comuna")
        col7, col8, col9 = st.columns(3)
        facility_type = col7.text_input("Tipo de establecimiento")
        category = col8.text_input("Categoría")
        rate = col9.text_input("RATE")
        col10, col11, col12 = st.columns(3)
        stage = col10.text_input("Etapa actual")
        status = col11.text_input("Estado")
        funding = col12.text_input("Financiamiento")
        progress = st.slider("Avance (%)", 0, 100, 0) / 100
        responsible = st.text_input("Encargado / responsable")
        cold1, cold2, cold3 = st.columns(3)
        contract_end = cold1.date_input("Término de contrato", value=None, format="DD-MM-YYYY")
        guarantee_end = cold2.date_input("Vigencia fiel cumplimiento", value=None, format="DD-MM-YYYY")
        guarantee_civil_end = cold3.date_input("Vigencia responsabilidad civil", value=None, format="DD-MM-YYYY")
        commitment = st.text_area("Compromiso Convenio de Programación (opcional)")
        comments = st.text_area("Comentario ejecutivo")
        submitted = st.form_submit_button("Guardar proyecto", type="primary")
        if submitted:
            if not name.strip():
                st.error("El nombre del proyecto es obligatorio.")
            else:
                record = {c: None for c in PROJECT_COLUMNS}
                record.update({
                    "id": make_id(bip, name), "grupo": grupo, "bip": bip.strip(), "name": name.strip(),
                    "province": province.strip(), "commune": commune.strip(), "facility_type": facility_type.strip(),
                    "category": category.strip(), "rate": rate.strip(), "stage": stage.strip(),
                    "status": status.strip(), "funding": funding.strip(), "progress": progress,
                    "owner_unit": owner_unit, "responsible": responsible.strip(),
                    "contract_end": contract_end, "guarantee_end": guarantee_end,
                    "guarantee_civil_end": guarantee_civil_end, "commitment": commitment.strip(),
                    "comments": comments.strip(),
                })
                upsert_projects(pd.DataFrame([record]), email)
                st.success(f"Proyecto «{name.strip()}» guardado y registrado en el historial.")
                st.cache_data.clear()

elif section == "Administración":
    st.subheader("Administración del sistema")
    st.caption(f"Fuente de datos activa: {backend_name()}")
    if str(st.query_params.get("tab", "")).lower() == "usuarios":
        users_tab, load_tab = st.tabs(["Usuarios y perfiles", "Carga de proyectos"])
    else:
        load_tab, users_tab = st.tabs(["Carga de proyectos", "Usuarios y perfiles"])
    with load_tab:
        st.caption("Acepta la Matriz completa (multihoja), la Planilla de Inversiones o la Planilla de Obras. El sistema reconoce automáticamente cada hoja.")
        st.markdown("#### Descargar formatos modelo")
        d1, d2, d3 = st.columns(3)
        d1.download_button(
            "⬇️ Modelo Matriz completa", model_workbook("matriz"),
            "Modelo_Matriz_Recursos_Fisicos.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        d2.download_button(
            "⬇️ Modelo Inversiones", model_workbook("inversiones"),
            "Modelo_Planilla_Inversiones.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        d3.download_button(
            "⬇️ Modelo Obras", model_workbook("obras"),
            "Modelo_Planilla_Obras.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.info("Complete una fila por proyecto o contrato, conserve los nombres de las columnas y luego cargue el archivo aquí.")
        st.link_button("✍️ Ingresar un proyecto manualmente", "?view=nuevo")
        uploaded = st.file_uploader("Cargar Matriz, Planilla de Obras o Planilla de Inversiones", type=["xlsx"])
        if uploaded:
            try:
                preview = parse_workbook(uploaded.getvalue())
                obras_n = int((preview["owner_unit"] == "Obras").sum())
                conv_n = int((preview["commitment"].fillna("").astype(str).str.len() > 0).sum())
                cartera_n = int((preview["owner_unit"] != "Convenio").sum())
                st.success(f"Se reconocieron {len(preview)} registros.")
                m1, m2, m3 = st.columns(3)
                m1.metric("Cartera de inversión", cartera_n)
                m2.metric("Obras y contratos", obras_n)
                m3.metric("Compromisos convenio", conv_n)
                st.dataframe(preview[["grupo", "bip", "name", "stage", "status", "owner_unit"]].head(40), hide_index=True, use_container_width=True)
                replace_demo = st.checkbox("Eliminar registros de demostración después de cargar")
                if st.button("Confirmar carga", type="primary"):
                    upsert_projects(preview, email)
                    if replace_demo:
                        delete_demo_projects()
                    st.success("Carga finalizada correctamente.")
                    st.rerun()
            except Exception as exc:
                st.error(f"No se pudo procesar la planilla: {exc}")
    with users_tab:
        users = read_users()
        if users.empty:
            users = pd.DataFrame(columns=["username", "display_name", "role", "unit", "active", "password_hash"])
        visible_users = users.drop(columns=["password_hash"], errors="ignore").copy()
        visible_users["password"] = ""
        edited_users = st.data_editor(
            visible_users, num_rows="dynamic", hide_index=True, use_container_width=True,
            column_config={
                "username": st.column_config.TextColumn("Usuario", required=True),
                "password": st.column_config.TextColumn("Nueva contraseña", help="Déjela vacía para conservar la actual."),
                "role": st.column_config.SelectboxColumn("Perfil", options=["Administrador", "Obras", "Inversiones", "Planificación", "Dirección", "Consulta"], required=True),
                "unit": st.column_config.SelectboxColumn("Unidad", options=["Administración", "Obras", "Inversiones", "Planificación", "Dirección", "Consulta"]),
                "active": st.column_config.CheckboxColumn("Activo"),
            },
        )
        st.caption("Cada usuario solo podrá visualizar o actualizar la unidad asignada. Las contraseñas se guardan como hash y nunca quedan visibles.")
        if st.button("Guardar usuarios y permisos", type="primary"):
            prepared = edited_users.rename(columns={"password": "password_hash"})
            replace_users(prepared, email)
            st.success("Usuarios y perfiles actualizados.")

st.caption(f"Última visualización: {datetime.now(timezone.utc).strftime('%d-%m-%Y %H:%M UTC')} · Los permisos de edición se validan en el servidor.")
