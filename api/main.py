import os
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import fetch_all, fetch_one
from admin_api import router as admin_router
from smart_update_api import router as smart_update_router

app = FastAPI(title="API de Reglamentaciones Crediticias", version="3.0.0")
origins = [item.strip() for item in os.getenv("FRONTEND_ORIGINS", "http://127.0.0.1:5500").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(admin_router)
app.include_router(smart_update_router)

DESTINATION_GROUPS = (
    {"codigo": "ADQ_CAMBIO_UNICA", "nombre": "Adquisición o cambio de vivienda única de ocupación permanente", "db_codes": ("ADQ_UNICA", "CAMBIO_UNICA")},
    {"codigo": "AMPL_REFAC_TERM_UNICA", "nombre": "Ampliación, refacción o terminación de vivienda única de ocupación permanente", "db_codes": ("AMPL_UNICA", "REFAC_UNICA", "TERM_UNICA")},
    {"codigo": "CONST_UNICA", "nombre": "Construcción de vivienda única sobre terreno propio", "db_codes": ("CONST_UNICA",)},
    {"codigo": "ADQ_CAMBIO_SEGUNDA", "nombre": "Adquisición o cambio de segunda vivienda", "db_codes": ("ADQ_SEGUNDA", "CAMBIO_SEGUNDA")},
    {"codigo": "AMPL_REFAC_TERM_SEGUNDA", "nombre": "Ampliación, refacción o terminación de segunda vivienda", "db_codes": ("AMPL_SEGUNDA", "REFAC_SEGUNDA", "TERM_SEGUNDA")},
    {"codigo": "CONST_SEGUNDA", "nombre": "Construcción de segunda vivienda sobre terreno propio", "db_codes": ("CONST_SEGUNDA",)},
)
DESTINATION_BY_CODE = {item["codigo"]: item for item in DESTINATION_GROUPS}


class QuoteRequest(BaseModel):
    reglamentacion: str = Field(pattern=r"^(800|802|802_01)$")
    fecha_acuerdo: date | None = None
    provincia: str = Field(min_length=1, max_length=10)
    organismo: str | None = Field(default=None, max_length=12)
    destino: str
    tipo_usuario: str
    valor_vivienda_uva: Decimal | None = Field(default=None, ge=0)
    modalidad_convenio: str | None = None
    usa_topeo: bool


BASE_FILTER = """
FROM dbo.Condiciones_Reglamentacion cr
JOIN dbo.Reglamentaciones r ON r.Reglamentacion_ID=cr.Reglamentacion_ID
JOIN dbo.Destinos d ON d.Destino_ID=cr.Destino_ID
JOIN dbo.Tipos_Usuario tu ON tu.Tipo_Usuario_ID=cr.Tipo_Usuario_ID
JOIN dbo.Ambito_Geografico_Provincias agp ON agp.Ambito_Geografico_ID=cr.Ambito_Geografico_ID
JOIN dbo.Provincias p ON p.Provincia_ID=agp.Provincia_ID
LEFT JOIN dbo.Modalidades_Convenio mc ON mc.Modalidad_Convenio_ID=cr.Modalidad_Convenio_ID
WHERE cr.Activa=1 AND r.Codigo=? AND p.Codigo=?
  AND (cr.Fecha_Desde IS NULL OR ? >= cr.Fecha_Desde)
  AND (cr.Fecha_Hasta IS NULL OR ? <= cr.Fecha_Hasta)
"""

PRODUCT_FILTER = BASE_FILTER.replace(
    "LEFT JOIN dbo.Modalidades_Convenio mc",
    "JOIN dbo.Condicion_Productos cp ON cp.Condicion_ID=cr.Condicion_ID\n"
    "JOIN dbo.Productos pr ON pr.Producto_ID=cp.Producto_ID\n"
    "LEFT JOIN dbo.Modalidades_Convenio mc",
)


def province_db_code(code: str) -> str:
    return {"N": "N", "T": "T", "RESTO": "A"}.get(code.upper(), code.upper())


def base_params(regulation: str, province: str, agreement_date: date | None) -> tuple:
    effective_date = agreement_date or date.today()
    return regulation, province_db_code(province), effective_date, effective_date


def destination_clause(ui_code: str) -> tuple[str, tuple]:
    group = DESTINATION_BY_CODE.get(ui_code)
    if not group:
        raise HTTPException(status_code=422, detail="El destino seleccionado no es válido")
    placeholders = ",".join("?" for _ in group["db_codes"])
    return f"d.Codigo IN ({placeholders})", tuple(group["db_codes"])


def organism_clause(regulation: str, organism: str | None) -> tuple[str, tuple]:
    if regulation != "802_01":
        return "", ()
    if not organism:
        raise HTTPException(status_code=422, detail="Debe seleccionar un organismo para la reglamentación 802_01")
    return """
    AND cr.Modalidad_Convenio_ID = (
        SELECT TOP (1) oc.Modalidad_Convenio_ID
        FROM dbo.Organismo_Condiciones_802_01 oc
        JOIN dbo.Organismos o
        ON o.Organismo_ID = oc.Organismo_ID
        WHERE oc.Activa = 1
        AND o.Activo = 1
        AND o.Codigo = ?
        AND oc.Tipo_Vivienda = d.Tipo_Vivienda
        ORDER BY oc.Vigencia_Desde DESC,
                oc.Organismo_Condicion_ID DESC
    )
    """, (organism,)


@app.get("/api/health")
def health():
    try:
        value = fetch_one("SELECT DB_NAME() AS database_name, 1 AS ok")
        return {"status": "ok", **value}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="No se pudo conectar con SQL Server") from exc


@app.get("/api/reglamentaciones")
def regulations():
    return fetch_all("SELECT Codigo AS codigo, Nombre AS nombre, Requiere_Fecha_Acuerdo AS requiere_fecha FROM dbo.Reglamentaciones WHERE Activa=1 ORDER BY Codigo")


@app.get("/api/provincias")
def provinces():
    return [
        {"codigo": "N", "nombre": "Misiones"},
        {"codigo": "T", "nombre": "Tucumán"},
        {"codigo": "RESTO", "nombre": "Resto de las provincias"},
    ]


@app.get("/api/organismos")
def organisms():
    return fetch_all("""
        WITH Ultima AS (
            SELECT oc.*,ROW_NUMBER() OVER(PARTITION BY oc.Organismo_ID,oc.Tipo_Vivienda ORDER BY oc.Vigencia_Desde DESC,oc.Organismo_Condicion_ID DESC) AS rn
            FROM dbo.Organismo_Condiciones_802_01 oc
            WHERE oc.Activa=1 AND oc.Vigencia_Desde<=CAST(GETDATE() AS date)
        )
        SELECT o.Codigo AS codigo,o.Nombre AS nombre,o.CUIT AS cuit,
               CAST(MAX(CASE WHEN oc.Tipo_Vivienda='UNICA' THEN mc.Tasa_Referencia_Pct END) AS decimal(7,2)) AS tasa_primera,
               CAST(MAX(CASE WHEN oc.Tipo_Vivienda='SEGUNDA' THEN mc.Tasa_Referencia_Pct END) AS decimal(7,2)) AS tasa_segunda,
               MAX(oc.Vigencia_Hasta) AS vigencia_hasta,
               CAST(
                    CASE
                        WHEN MAX(
                            CASE
                                WHEN CAST(GETDATE() AS date)
                                        BETWEEN oc.Vigencia_Desde AND oc.Vigencia_Hasta
                                THEN 1
                                ELSE 0
                            END
                        ) = 1
                        THEN 1
                        ELSE 0
                    END
                    AS bit) AS vigente
        FROM dbo.Organismos o
        JOIN Ultima oc ON oc.Organismo_ID=o.Organismo_ID AND oc.rn=1
        JOIN dbo.Modalidades_Convenio mc ON mc.Modalidad_Convenio_ID=oc.Modalidad_Convenio_ID
        WHERE o.Activo=1
        GROUP BY o.Codigo,o.Nombre,o.CUIT
        ORDER BY o.Nombre
    """)


@app.get("/api/destinos")
def destinations(reglamentacion: str, provincia: str, fecha_acuerdo: date | None = None, organismo: str | None = None):
    org_sql, org_params = organism_clause(reglamentacion, organismo)
    rows = fetch_all("SELECT DISTINCT d.Codigo AS codigo " + BASE_FILTER + org_sql, base_params(reglamentacion, provincia, fecha_acuerdo) + org_params)
    available = {row["codigo"] for row in rows}
    return [{"codigo": item["codigo"], "nombre": item["nombre"]} for item in DESTINATION_GROUPS if available.intersection(item["db_codes"])]


@app.get("/api/usuarios")
def users(reglamentacion: str, provincia: str, destino: str, fecha_acuerdo: date | None = None, organismo: str | None = None):
    dest_sql, dest_params = destination_clause(destino)
    org_sql, org_params = organism_clause(reglamentacion, organismo)
    sql = "SELECT DISTINCT tu.Codigo AS codigo,tu.Nombre AS nombre " + BASE_FILTER + f" AND {dest_sql}" + org_sql + " ORDER BY tu.Nombre"
    return fetch_all(sql, base_params(reglamentacion, provincia, fecha_acuerdo) + dest_params + org_params)


@app.get("/api/opciones")
def options(reglamentacion: str, provincia: str, destino: str, tipo_usuario: str, fecha_acuerdo: date | None = None, organismo: str | None = None):
    dest_sql, dest_params = destination_clause(destino)
    org_sql, org_params = organism_clause(reglamentacion, organismo)
    tail = f" AND {dest_sql} AND tu.Codigo=?" + org_sql
    params = base_params(reglamentacion, provincia, fecha_acuerdo) + dest_params + (tipo_usuario,) + org_params
    sql = """SELECT CAST(MAX(CASE WHEN cr.UVA_Desde IS NOT NULL OR cr.UVA_Hasta IS NOT NULL THEN 1 ELSE 0 END) AS bit) AS requiere_uva,
             COUNT(DISTINCT cr.Modalidad_Convenio_ID) AS cantidad_modalidades,
             CAST(MIN(CAST(cr.Permite_Topeo AS tinyint)) AS bit) AS topeo_min,
             CAST(MAX(CAST(cr.Permite_Topeo AS tinyint)) AS bit) AS topeo_max """ + BASE_FILTER + tail
    summary = fetch_one(sql, params)
    modalities = fetch_all("SELECT DISTINCT mc.Codigo AS codigo,mc.Nombre AS nombre,mc.Tasa_Referencia_Pct AS tasa " + BASE_FILTER + tail + " AND mc.Modalidad_Convenio_ID IS NOT NULL ORDER BY mc.Tasa_Referencia_Pct DESC", params)
    if not summary or summary["topeo_min"] is None:
        raise HTTPException(status_code=404, detail="No existen condiciones para la selección")
    return {**summary, "modalidades": modalities}


@app.post("/api/cotizar")
def quote(payload: QuoteRequest):
    if payload.reglamentacion in {"800", "802"} and payload.fecha_acuerdo is None:
        raise HTTPException(status_code=422, detail="La fecha de acuerdo es obligatoria")
    dest_sql, dest_params = destination_clause(payload.destino)
    org_sql, org_params = organism_clause(payload.reglamentacion, payload.organismo)
    sql = """SELECT cr.Condicion_ID AS condicion_id,cr.Codigo_Condicion AS codigo_condicion,
                    CAST(cr.Tasa_Aplicable_Pct AS decimal(7,2)) AS tasa_aplicable_pct,
                    cr.Permite_Topeo AS permite_topeo,cr.Cobra_Prima_Topeo AS cobra_prima_topeo,
                    MAX(CASE WHEN cp.Rol_Producto='UNICO' THEN pr.Codigo END) AS codigo_producto,
                    MAX(CASE WHEN cp.Rol_Producto='DESEMBOLSO' THEN pr.Codigo END) AS codigo_desembolso,
                    MAX(CASE WHEN cp.Rol_Producto='CONSOLIDACION' THEN pr.Codigo END) AS codigo_consolidacion,
                    cr.Referencia_Fuente AS referencia_fuente,cr.Observaciones AS observaciones """ + PRODUCT_FILTER + f"""
      AND {dest_sql} AND tu.Codigo=?""" + org_sql + """
      AND (cr.UVA_Desde IS NULL OR (? IS NOT NULL AND (? > cr.UVA_Desde OR (?=cr.UVA_Desde AND cr.UVA_Desde_Inclusive=1))))
      AND (cr.UVA_Hasta IS NULL OR (? IS NOT NULL AND (? < cr.UVA_Hasta OR (?=cr.UVA_Hasta AND cr.UVA_Hasta_Inclusive=1))))
      AND (? IS NULL OR cr.Modalidad_Convenio_ID IS NULL OR mc.Codigo=?) AND cr.Permite_Topeo=?
    GROUP BY cr.Condicion_ID,cr.Codigo_Condicion,cr.Tasa_Aplicable_Pct,cr.Permite_Topeo,cr.Cobra_Prima_Topeo,cr.Referencia_Fuente,cr.Observaciones"""
    uva = payload.valor_vivienda_uva
    params = base_params(payload.reglamentacion, payload.provincia, payload.fecha_acuerdo) + dest_params + (payload.tipo_usuario,) + org_params + (uva, uva, uva, uva, uva, uva, payload.modalidad_convenio, payload.modalidad_convenio, payload.usa_topeo)
    rows = fetch_all(sql, params)
    if not rows:
        raise HTTPException(status_code=404, detail="No se encontró una condición normativa para esta combinación")

    business_fields = ("tasa_aplicable_pct", "permite_topeo", "cobra_prima_topeo", "codigo_producto", "codigo_desembolso", "codigo_consolidacion")
    unique = {tuple(row[field] for field in business_fields): row for row in rows}
    if len(unique) > 1:
        raise HTTPException(status_code=409, detail="El grupo de destino contiene condiciones diferentes; debe desagregarse en la interfaz")
    result = next(iter(unique.values()))
    result["tasa_aplicable_pct"] = float(result["tasa_aplicable_pct"])

    if payload.reglamentacion == "802_01":
        metadata = fetch_one("""
            SELECT TOP(1) o.Nombre AS organismo_nombre,o.CUIT AS organismo_cuit,oc.Vigencia_Hasta AS vigencia_hasta,
                   oc.Grupo_Pauta AS grupo_pauta,oc.Adicional_Topeo_Pct AS adicional_topeo_pct,
                   oc.Aplica_Circular_3214 AS aplica_circular_3214,
                   CAST(CASE WHEN oc.Vigencia_Hasta >= CAST(GETDATE() AS date) THEN 1 ELSE 0 END AS bit) AS organismo_vigente
            FROM dbo.Organismos o
            JOIN dbo.Organismo_Condiciones_802_01 oc ON oc.Organismo_ID=o.Organismo_ID
            JOIN dbo.Modalidades_Convenio mc ON mc.Modalidad_Convenio_ID=oc.Modalidad_Convenio_ID
            WHERE o.Codigo=? AND oc.Tipo_Vivienda=? AND mc.Tasa_Referencia_Pct=?
            ORDER BY oc.Vigencia_Desde DESC, oc.Organismo_Condicion_ID DESC
        """, (payload.organismo, "SEGUNDA" if "SEGUNDA" in payload.destino else "UNICA", result["tasa_aplicable_pct"]))
        if metadata:
            result.update(metadata)
    return result


@app.get("/api/consolidaciones/{codigo_desembolso}")
def consolidation(codigo_desembolso: str):
    rows = fetch_all("""
        SELECT Codigo_Desembolso AS codigo_desembolso,Codigo_Consolidacion AS codigo_consolidacion,Reglamentacion AS reglamentacion
        FROM dbo.VW_Producto_Equivalencias_Vigentes
        WHERE UPPER(Codigo_Desembolso)=UPPER(?)
        ORDER BY Reglamentacion,Fecha_Desde DESC
    """, (codigo_desembolso.strip(),))
    if not rows:
        raise HTTPException(status_code=404, detail="No existe una consolidación asociada a ese producto de desembolso")
    consolidations = {row["codigo_consolidacion"] for row in rows}
    if len(consolidations) > 1:
        raise HTTPException(status_code=409, detail="El producto posee consolidaciones vigentes diferentes según reglamentación")
    result = rows[0]
    result["reglamentaciones"] = [row["reglamentacion"] for row in rows]
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "8000")), reload=True)
