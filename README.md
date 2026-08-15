# Panel de Recursos Físicos SSMOC

Aplicación Streamlit para el seguimiento autogestionado de proyectos de Obras, Inversiones y Planificación del Servicio de Salud Metropolitano Occidente.

## Funcionalidades

- Dashboard ejecutivo y acciones prioritarias.
- Generación de informes institucionales en formato imprimible/PDF: informe gerencial integral, informe de inversiones e informe técnico de obras y contratos.
- Informes con portada y logo SSMOC, resumen ejecutivo automático, KPI con denominadores, índice de control, semáforo de alertas, decisiones requeridas, plan de corto plazo, detalle trazable y ficha metodológica.
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

## Actualización integrada desde el dashboard

El perfil Administrador dispone del botón **Actualizar cartera** en la barra del panel. Este abre una ventana modal sin abandonar el dashboard y permite seleccionar uno o varios archivos `.xlsx` en la misma operación.

La ventana de carga:

- reconoce automáticamente la Matriz completa, la Planilla de Inversiones y la Planilla de Obras;
- valida cada archivo por separado;
- descarta filas separadoras y normaliza los campos mediante el importador institucional;
- consolida duplicados por identificador de proyecto;
- compara cuántos registros son nuevos y cuántos serán actualizados;
- muestra la distribución entre Inversiones, Obras, Planificación y Convenio;
- exige revisión y confirmación explícita antes de escribir en la base central;
- bloquea la actualización si alguno de los archivos presenta observaciones.

La escritura se ejecuta en el servidor, conserva los controles de acceso y registra al usuario responsable en `HISTORIAL`. Las credenciales de Google Sheets nunca se envían al navegador.

### Planillas reconocidas

- `00 MATRIZ PROYECTOS 2026.xlsx`: hojas de Inversiones, Planificación y Convenio.
- `Planilla Inversiones.xlsx`: cartera de iniciativas de inversión.
- `Planilla Obras.xlsx`: contratos, vigencias, garantías y siguientes etapas.

El Administrador puede cargar los tres archivos juntos. Antes de confirmar se presenta un resumen por archivo, vista previa de registros y recuento de nuevos, actualizados y duplicados.

## Flujo de datos

El Administrador carga la información desde el propio dashboard. Python valida y normaliza los libros, actualiza la base central y registra la operación en el historial. Los usuarios autorizados visualizan o actualizan solamente los proyectos correspondientes a su perfil y unidad.
