# Cotizador y administración de reglamentaciones

Aplicación interna para consultar y mantener las reglamentaciones 800, 802 y 802_01. Utiliza HTML/CSS/JavaScript, FastAPI, SQL Server y autenticación integrada de Windows.

## Instalación de esta actualización

1. Realizar un backup de la base y de la versión actual de `api` y `frontend`.
2. Ejecutar en SQL Server Management Studio, en este orden:
   - `04_Organismos_802_01.sql`, si todavía no fue aplicado.
   - `05_Modulo_Administracion.sql`.
   - `06_Asistente_Actualizacion_Automatica.sql`.
3. Copiar las carpetas `api`, `frontend` y `plantillas` del paquete.
4. Conservar o completar `api/.env`. Para autenticación SQL integrada debe contener `DB_TRUSTED_CONNECTION=yes`.
5. Ejecutar `iniciar_api.bat`. El BAT instalará también los lectores de Word, PDF y Excel.
6. Ejecutar `iniciar_frontend.bat`.
7. Abrir `http://127.0.0.1:5500` y presionar `Ctrl + F5`.

La migración asigna el rol `ADMINISTRADOR` al usuario Windows que la ejecuta (`ORIGINAL_LOGIN()`). Si el usuario con el que se ejecuta Python es diferente, agregarlo en `dbo.Usuarios_Aplicacion`.

```sql
INSERT dbo.Usuarios_Aplicacion (Usuario_Windows, Nombre_Mostrar, Rol)
VALUES (N'DOMINIO\usuario', N'Nombre y apellido', 'ADMINISTRADOR');
```

## Flujo operativo

### Asistente automático recomendado

1. En Administración, subir el Word, PDF con texto o Excel recibido.
2. Indicar la fecha desde la cual deben regir los nuevos valores.
3. Revisar cada propuesta junto con la fila o párrafo que la originó.
4. Marcar únicamente las propuestas correctas y crear la carga.
5. Continuar con la aprobación y publicación habituales. El asistente nunca publica por sí solo.

Los datos vencidos, ambiguos o sin dimensiones suficientes se muestran como `REQUIERE_REVISION` y no se seleccionan automáticamente. Los PDF escaneados sin texto requieren OCR o el Word original.

1. El CARGADOR descarga la plantilla oficial.
2. Completa solamente las hojas que necesita y sube el `.xlsx`.
3. La API valida maestros, formatos, tasas, productos, fechas, duplicados y relaciones.
4. La web muestra altas, modificaciones, bajas, errores y valores anteriores/nuevos.
5. Un APROBADOR distinto del cargador aprueba o rechaza.
6. Una carga aprobada se publica en una única transacción.
7. Cada cambio queda registrado en `dbo.Auditoria_Cambios_Normativos`.

Los cambios puntuales realizados desde la web crean una carga manual y recorren exactamente el mismo circuito.

## Roles

- `CONSULTOR`: no accede a Administración.
- `CARGADOR`: crea y valida cargas.
- `APROBADOR`: aprueba, rechaza y publica; no puede aprobar su propia carga.
- `ADMINISTRADOR`: además mantiene usuarios y roles.

El doble control está activo por defecto. No configurar `ALLOW_SELF_APPROVAL=true` fuera de una prueba local.

## Versionado

- Una nueva equivalencia cierra la anterior el día previo a su `Fecha_Desde`.
- Una nueva condición con la misma `Clave_Mantenimiento` crea una nueva versión y cierra la anterior.
- Una nueva tasa de organismo se versiona por `Vigencia_Desde`.
- Una baja finaliza la vigencia o desactiva el maestro; nunca elimina historia.
- El Excel original, su hash SHA-256, usuario, aprobación y publicación quedan guardados.

## Autenticación Windows

### Uso local

Con `TRUST_WINDOWS_AUTH_HEADER=false`, la API identifica la cuenta Windows que ejecuta Python. Esto sirve para desarrollo o para una instalación individual.

### Intranet multiusuario

Para identificar a cada empleado debe publicarse el sitio detrás de IIS con Windows Authentication:

- IIS entrega el usuario autenticado a la API en `X-Remote-User`.
- Configurar `TRUST_WINDOWS_AUTH_HEADER=true`.
- Mantener Uvicorn escuchando únicamente en `127.0.0.1`; su puerto no debe exponerse a otros equipos.
- IIS debe reemplazar el encabezado y eliminar cualquier valor enviado por el cliente.
- Servir frontend y API bajo HTTPS y el mismo dominio interno.

No habilitar la confianza del encabezado si los usuarios pueden conectarse directamente al puerto de FastAPI.

## Tablas agregadas

- `Usuarios_Aplicacion`
- `Cargas_Normativas`
- `Carga_Normativa_Detalles`
- `Carga_Normativa_Errores`
- `Auditoria_Cambios_Normativos`
- `Producto_Equivalencias`
- `VW_Producto_Equivalencias_Vigentes`
- `Documentos_Normativos`
- `Documento_Hallazgos`

También se agregan columnas de versionado a `Condiciones_Reglamentacion` y `Organismo_Condiciones_802_01`.

## Pruebas mínimas

- `http://127.0.0.1:8000/api/health` debe responder `status: ok`.
- `http://127.0.0.1:8000/api/admin/me` debe mostrar el usuario y rol.
- Administración debe permitir descargar la plantilla.
- Una plantilla vacía debe rechazarse por no contener registros.
- Una tasa inexistente debe quedar `CON_ERRORES`.
- El cargador no debe poder aprobar su propia carga.
- Después de publicar, el cotizador y la conversión de productos deben mostrar la nueva vigencia.
