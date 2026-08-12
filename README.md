# Panel de Recursos Físicos SSMOC

Aplicación Streamlit para el seguimiento autogestionado de proyectos de Obras, Inversiones y Planificación del Servicio de Salud Metropolitano Occidente.

## Carga de información

El panel admite dos vías, ambas desde la sesión de Administrador (o unidades con permiso de edición):

**Carga masiva (Administración → Carga de proyectos).** Sube uno de estos archivos `.xlsx` y el sistema reconoce automáticamente cada hoja:

- `00_MATRIZ_PROYECTOS_2026.xlsx` — matriz completa: hoja de Inversión, Planificación (se omite si duplica a Inversión) y Convenio de Programación.
- `Planilla_Inversiones.xlsx` — cartera de inversión con compromisos de octubre.
- `Planilla_Obras.xlsx` — contratos, fechas de término, garantías (fiel cumplimiento y responsabilidad civil) y siguientes etapas.

El importador detecta la fila de encabezados aunque haya banners o columnas en blanco, descarta filas separadoras de grupo, normaliza los códigos BIP y adjunta los compromisos del convenio por código BIP. Antes de confirmar se muestra un resumen por Cartera / Obras / Convenio.

**Carga manual (Nuevo proyecto).** Formulario para registrar un proyecto individual. Si el código BIP y el nombre coinciden con uno existente, se actualiza en lugar de duplicarse.

Cada registro alimenta las tres pestañas del panel visual: Cartera de Inversión (grupos A–G, RATE, etapa, estado, financiamiento), Obras y Contratos (vigencias y garantías con semáforo) y Convenio de Programación (compromisos por BIP).

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
- Acceso interno mediante usuario y contraseña, con perfiles y contraseñas protegidas mediante hash.

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
5. Configurar `ADMIN_USERNAME` y `ADMIN_PASSWORD`, e ingresar los demás usuarios desde Administración.

## Google Sheets autogestionado

1. Crear una planilla privada, sin compartirla con los usuarios finales.
2. Crear una cuenta de servicio de Google y compartir la planilla únicamente con su `client_email` como Editor.
3. Configurar `GOOGLE_SHEET_ID` y `[gcp_service_account]` en los Secrets de Streamlit.
4. Configurar el usuario y contraseña iniciales del Administrador en los Secrets de Streamlit.
5. El sistema crea las hojas `PROYECTOS`, `USUARIOS`, `HISTORIAL` y `CATALOGOS`.
6. Ingresar inicialmente como `ADMIN_EMAIL` y registrar los demás correos y perfiles desde `?view=administracion`.

La autorización se valida en Python. Los usuarios no requieren ni deben recibir acceso directo a la planilla, y sus contraseñas se almacenan exclusivamente como hashes bcrypt.

No se deben subir planillas, bases de datos, credenciales ni documentos institucionales al repositorio.

## Flujo de datos

El Administrador carga la matriz desde la aplicación. Los usuarios autorizados actualizan solamente los proyectos de su unidad; Dirección y Consulta mantienen acceso de lectura. Cada actualización queda registrada en `audit_log`.
