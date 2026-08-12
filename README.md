# Panel de Recursos Físicos SSMOC

Aplicación Streamlit para el seguimiento autogestionado de proyectos de Obras, Inversiones y Planificación del Servicio de Salud Metropolitano Occidente.

## Funcionalidades

- Dashboard ejecutivo y acciones prioritarias.
- Panel HTML original integrado como vista principal y alimentado desde la base central.
- Cartera filtrable y exportable.
- Perfiles: Administrador, Obras, Inversiones, Planificación, Dirección y Consulta.
- Edición limitada a la unidad del usuario.
- Carga masiva desde las planillas institucionales existentes.
- Historial de modificaciones.
- PostgreSQL para producción y SQLite para desarrollo local.
- Google Sheets privado como alternativa autogestionada, con perfiles e historial.
- Preparado para autenticación Microsoft Entra mediante OIDC.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Sin secretos configurados se inicia en modo demostración y crea una base SQLite local, excluida de Git.

## Producción

1. Crear una base PostgreSQL privada.
2. Copiar las variables de `.streamlit/secrets.example.toml` al panel Secrets de Streamlit Cloud.
3. Definir `DATABASE_URL` y `ADMIN_EMAIL`.
4. Desplegar `app.py` desde este repositorio.
5. Configurar Microsoft Entra/OIDC con apoyo de Informática.

## Google Sheets autogestionado

1. Crear una planilla privada, sin compartirla con los usuarios finales.
2. Crear una cuenta de servicio de Google y compartir la planilla únicamente con su `client_email` como Editor.
3. Configurar `GOOGLE_SHEET_ID` y `[gcp_service_account]` en los Secrets de Streamlit.
4. Configurar OIDC para que cada persona ingrese con su cuenta institucional.
5. El sistema crea las hojas `PROYECTOS`, `USUARIOS`, `HISTORIAL` y `CATALOGOS`.
6. Ingresar inicialmente como `ADMIN_EMAIL` y registrar los demás correos y perfiles desde `?view=administracion`.

La autorización se valida en Python; los usuarios no requieren ni deben recibir acceso directo a la planilla de Google.

No se deben subir planillas, bases de datos, credenciales ni documentos institucionales al repositorio.

## Flujo de datos

El Administrador carga la matriz desde la aplicación. Los usuarios autorizados actualizan solamente los proyectos de su unidad; Dirección y Consulta mantienen acceso de lectura. Cada actualización queda registrada en `audit_log`.
