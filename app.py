from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from services.database import get_user, init_db, read_projects, upsert_projects
from services.importer import PROJECT_COLUMNS, parse_workbook


st.set_page_config(page_title="Recursos Físicos SSMOC", page_icon="🏥", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.5rem;max-width:1500px}.hero{padding:1.4rem 1.6rem;border-radius:18px;color:white;background:linear-gradient(120deg,#075985,#0f766e);margin-bottom:1rem}.hero h1{margin:0;font-size:2rem}.hero p{margin:.35rem 0 0;opacity:.88}.stMetric{background:white;border:1px solid #e5e7eb;padding:1rem;border-radius:14px}.badge{display:inline-block;padding:.2rem .65rem;border-radius:99px;background:#dbeafe;color:#1e3a8a;font-weight:700;font-size:.78rem}
</style>
""", unsafe_allow_html=True)


def secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets[name])
    except (KeyError, FileNotFoundError):
        return default


def identity() -> tuple[str, str]:
    try:
        if st.user.is_logged_in:
            return str(st.user.email), str(getattr(st.user, "name", st.user.email))
    except Exception:
        pass
    email = secret("ADMIN_EMAIL", "admin@demo.local")
    return email, "Modo demostración"


def days_status(value) -> str:
    if value is None or pd.isna(value):
        return "Sin fecha"
    remaining = (pd.to_datetime(value).date() - date.today()).days
    if remaining < 0:
        return "Vencido"
    if remaining <= 30:
        return "Por vencer"
    return "Vigente"


init_db()
email, display_name = identity()
user = get_user(email, secret("ADMIN_EMAIL", "admin@demo.local"))
if not user.get("active", True):
    st.error("El usuario se encuentra deshabilitado.")
    st.stop()

st.markdown('<div class="hero"><h1>Panel de Recursos Físicos</h1><p>Seguimiento integrado de obras, inversiones, compromisos y alertas · SSMOC</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Sesión")
    st.write(display_name)
    st.markdown(f'<span class="badge">{user["role"]}</span>', unsafe_allow_html=True)
    st.caption(email)
    if user["role"] != "Administrador" and user.get("unit"):
        st.caption(f'Unidad: {user["unit"]}')
    section = st.radio("Navegación", ["Resumen ejecutivo", "Cartera de proyectos", "Actualizar proyecto", "Administración"] if user["role"] == "Administrador" else ["Resumen ejecutivo", "Cartera de proyectos", "Actualizar proyecto"] if user["role"] not in {"Dirección", "Consulta"} else ["Resumen ejecutivo", "Cartera de proyectos"])

data = read_projects()
if user["role"] not in {"Administrador", "Dirección", "Consulta"} and user.get("unit"):
    data = data[data["owner_unit"].fillna("").str.lower() == user["unit"].lower()]

if section == "Resumen ejecutivo":
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
            st.plotly_chart(px.bar(counts, x="Proyectos", y="Estado", orientation="h", color="Proyectos", color_continuous_scale="Teal"), use_container_width=True)
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

elif section == "Administración":
    st.subheader("Administración y carga masiva")
    st.warning("Antes de cargar información real, configure PostgreSQL y mantenga el repositorio sin archivos institucionales.")
    uploaded = st.file_uploader("Cargar Matriz, Planilla de Obras o Planilla de Inversiones", type=["xlsx"])
    if uploaded:
        try:
            preview = parse_workbook(uploaded.getvalue())
            st.success(f"Se reconocieron {len(preview)} proyectos.")
            st.dataframe(preview[["bip", "name", "stage", "status", "owner_unit"]].head(30), hide_index=True, use_container_width=True)
            replace_demo = st.checkbox("Eliminar registros de demostración después de cargar")
            if st.button("Confirmar carga", type="primary"):
                upsert_projects(preview, email)
                if replace_demo:
                    from services.database import engine
                    from sqlalchemy import text
                    with engine().begin() as conn:
                        conn.execute(text("DELETE FROM projects WHERE id LIKE 'demo-%'"))
                st.success("Carga finalizada correctamente.")
                st.rerun()
        except Exception as exc:
            st.error(f"No se pudo procesar la planilla: {exc}")

st.caption(f"Última visualización: {datetime.now(timezone.utc).strftime('%d-%m-%Y %H:%M UTC')} · Los permisos de edición se validan en el servidor.")

