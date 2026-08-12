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

No se deben subir planillas, bases de datos, credenciales ni documentos institucionales al repositorio.

## Flujo de datos

El Administrador carga la matriz desde la aplicación. Los usuarios autorizados actualizan solamente los proyectos de su unidad; Dirección y Consulta mantienen acceso de lectura. Cada actualización queda registrada en `audit_log`.
