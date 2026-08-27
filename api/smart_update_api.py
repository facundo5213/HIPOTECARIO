import hashlib
import json
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from admin_api import load_detail, normalize_record, persist_load, references, require_role
from db import fetch_all, fetch_one, get_connection
from document_analyzer import analyze

router = APIRouter(prefix="/api/admin/asistente", tags=["Asistente de actualización normativa"])
MAX_FILE_SIZE = 20 * 1024 * 1024
SUPPORTED_EXTENSIONS = {"docx", "pdf", "xlsx"}

class CreateLoadRequest(BaseModel):
   hallazgo_ids: list[int] = Field(min_length=1, max_length=1500)

def document_detail(document_id: int, user: dict) -> dict:
   header = fetch_one("""SELECT Documento_ID AS documento_id,Nombre_Archivo AS nombre_archivo,Extension AS extension,
       Estado AS estado,Reglamentacion_Detectada AS reglamentacion,Confianza_Global AS confianza,
       Total_Hallazgos AS total_hallazgos,Total_Propuestas AS total_propuestas,Total_Revisiones AS total_revisiones,
       Usuario_Carga AS usuario_carga,Fecha_Carga AS fecha_carga,Fecha_Analisis AS fecha_analisis,
       Carga_ID AS carga_id,Fecha_Propuesta AS fecha_propuesta,Observaciones AS observaciones,Error_Analisis AS error_analisis
       FROM dbo.Documentos_Normativos WHERE Documento_ID=?""", (document_id,))
   if not header:
       raise HTTPException(status_code=404, detail="El documento no existe")
   header["hallazgos"] = fetch_all("""SELECT Hallazgo_ID AS hallazgo_id,Tipo_Hallazgo AS tipo,Ubicacion AS ubicacion,
       Evidencia AS evidencia,Confianza AS confianza,Estado AS estado,Tipo_Registro_Propuesto AS tipo_registro,
       Clave_Propuesta AS clave,Datos_Extraidos_JSON AS datos_extraidos_json,
       Datos_Propuestos_JSON AS datos_propuestos_json,Motivo_Revision AS motivo,Seleccionado AS seleccionado
       FROM dbo.Documento_Hallazgos WHERE Documento_ID=?
       ORDER BY CASE WHEN Tipo_Registro_Propuesto IS NOT NULL THEN 0 ELSE 1 END,Confianza DESC,Hallazgo_ID""", (document_id,))
   return header

@router.post("/analizar")
async def analyze_document(
   file: UploadFile = File(...),
   fecha_desde: date = Form(...),
   observaciones: str | None = Form(default=None),
   user: dict = Depends(require_role("CARGADOR")),
):
   filename = Path(file.filename or "").name
   extension = Path(filename).suffix.lower().lstrip(".")
   if extension not in SUPPORTED_EXTENSIONS:
       raise HTTPException(status_code=422, detail="Formatos permitidos: Word .docx, PDF .pdf o Excel .xlsx")
   content = await file.read(MAX_FILE_SIZE + 1)
   if not content:
       raise HTTPException(status_code=422, detail="El archivo está vacío")
   if len(content) > MAX_FILE_SIZE:
       raise HTTPException(status_code=413, detail="El archivo supera el máximo de 20 MB")
   digest = hashlib.sha256(content).hexdigest()
   previous = fetch_one("SELECT Documento_ID AS documento_id FROM dbo.Documentos_Normativos WHERE Hash_Archivo=? AND Fecha_Propuesta=?", (digest, fecha_desde))
   if previous:
       return document_detail(previous["documento_id"], user)
   with get_connection() as connection:
       cursor = connection.cursor()
       cursor.execute("""INSERT dbo.Documentos_Normativos
           (Nombre_Archivo,Extension,Tipo_MIME,Hash_Archivo,Fecha_Propuesta,Archivo_Original,Estado,Usuario_Carga,Observaciones)
           OUTPUT INSERTED.Documento_ID VALUES (?,?,?,?,?,?,'ANALIZANDO',?,?)""",
           (filename, extension, file.content_type, digest, fecha_desde, content, user["usuario"], observaciones))
       document_id = int(cursor.fetchone()[0])
       connection.commit()
   try:
       organisms = fetch_all("SELECT Codigo AS codigo,Nombre AS nombre,CUIT AS cuit FROM dbo.Organismos")
       products = [item["codigo"] for item in fetch_all("SELECT Codigo AS codigo FROM dbo.Productos")]
       # Misma condición que usa persist_record para decidir qué fila de Producto_Equivalencias
       # cerraría una carga nueva: así el análisis y la publicación quedan sincronizados.
       equivalence_rows = fetch_all("""
           SELECT pd.Codigo AS desembolso, r.Codigo AS reglamentacion, pc.Codigo AS consolidacion
           FROM dbo.Producto_Equivalencias pe
           JOIN dbo.Productos pd ON pd.Producto_ID = pe.Producto_Desembolso_ID
           JOIN dbo.Productos pc ON pc.Producto_ID = pe.Producto_Consolidacion_ID
           JOIN dbo.Reglamentaciones r ON r.Reglamentacion_ID = pe.Reglamentacion_ID
           WHERE pe.Activa = 1 AND pe.Fecha_Desde < ? AND (pe.Fecha_Hasta IS NULL OR pe.Fecha_Hasta >= ?)
       """, (fecha_desde, fecha_desde))
       existing_equivalences = {f"{row['desembolso']}|{row['reglamentacion']}": row["consolidacion"] for row in equivalence_rows}
       # Condiciones_Reglamentacion es la tabla que realmente alimenta "Consulta normativa"
       # (Producto_Equivalencias sólo alimenta "Conversión de productos"). Se buscan las
       # condiciones vigentes que usan cada producto (como UNICO o como DESEMBOLSO) para
       # poder renovarlas cuando la planilla marca ¿CAMBIÓ?=SI sobre ese producto.
       condition_rows = fetch_all("""
           SELECT cr.Clave_Mantenimiento AS clave_mantenimiento, r.Codigo AS reglamentacion,
                  ag.Codigo AS ambito_geografico, d.Codigo AS destino, tu.Codigo AS tipo_usuario, mc.Codigo AS modalidad_convenio,
                  cr.UVA_Desde AS uva_desde, cr.UVA_Desde_Inclusive AS uva_desde_inclusive,
                  cr.UVA_Hasta AS uva_hasta, cr.UVA_Hasta_Inclusive AS uva_hasta_inclusive,
                  CAST(cr.Tasa_Aplicable_Pct AS float) AS tasa_aplicable_pct, cr.Permite_Topeo AS permite_topeo, cr.Cobra_Prima_Topeo AS cobra_prima_topeo,
                  cr.Referencia_Fuente AS referencia_fuente, cr.Observaciones AS observaciones,
                  pu.Codigo AS codigo_producto, pd2.Codigo AS codigo_desembolso, pc2.Codigo AS codigo_consolidacion
           FROM dbo.Condiciones_Reglamentacion cr
           JOIN dbo.Reglamentaciones r ON r.Reglamentacion_ID = cr.Reglamentacion_ID
           JOIN dbo.Ambitos_Geograficos ag ON ag.Ambito_Geografico_ID = cr.Ambito_Geografico_ID
           JOIN dbo.Destinos d ON d.Destino_ID = cr.Destino_ID
           JOIN dbo.Tipos_Usuario tu ON tu.Tipo_Usuario_ID = cr.Tipo_Usuario_ID
           LEFT JOIN dbo.Modalidades_Convenio mc ON mc.Modalidad_Convenio_ID = cr.Modalidad_Convenio_ID
           LEFT JOIN dbo.Condicion_Productos cpu ON cpu.Condicion_ID = cr.Condicion_ID AND cpu.Rol_Producto = 'UNICO'
           LEFT JOIN dbo.Productos pu ON pu.Producto_ID = cpu.Producto_ID
           LEFT JOIN dbo.Condicion_Productos cpd ON cpd.Condicion_ID = cr.Condicion_ID AND cpd.Rol_Producto = 'DESEMBOLSO'
           LEFT JOIN dbo.Productos pd2 ON pd2.Producto_ID = cpd.Producto_ID
           LEFT JOIN dbo.Condicion_Productos cpc ON cpc.Condicion_ID = cr.Condicion_ID AND cpc.Rol_Producto = 'CONSOLIDACION'
           LEFT JOIN dbo.Productos pc2 ON pc2.Producto_ID = cpc.Producto_ID
           WHERE cr.Activa = 1 AND (cr.Fecha_Hasta IS NULL OR cr.Fecha_Hasta >= ?)
             AND (pu.Codigo IS NOT NULL OR pd2.Codigo IS NOT NULL)
       """, (fecha_desde,))
       existing_conditions = {}
       for row in condition_rows:
           anchor = row["codigo_producto"] or row["codigo_desembolso"]
           existing_conditions.setdefault(f"{anchor}|{row['reglamentacion']}", []).append(row)
       result = analyze(content, extension, document_id, fecha_desde, organisms, products, existing_equivalences, existing_conditions)
       with get_connection() as connection:
           cursor = connection.cursor()
           for item in result["findings"]:
               cursor.execute("""INSERT dbo.Documento_Hallazgos
                   (Documento_ID,Tipo_Hallazgo,Ubicacion,Evidencia,Confianza,Estado,Tipo_Registro_Propuesto,
                    Clave_Propuesta,Datos_Extraidos_JSON,Datos_Propuestos_JSON,Motivo_Revision,Seleccionado)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                   document_id, item["type"], item["location"], item["evidence"], item["confidence"], item["status"],
                   item["proposal_type"], item["proposal_key"], json.dumps(item["extracted"], ensure_ascii=False),
                   json.dumps(item["proposed"], ensure_ascii=False) if item["proposed"] else None,
                   item["reason"], 1 if item["selected"] else 0,
               ))
           state = "REQUIERE_REVISION" if result["total_reviews"] else "ANALIZADO"
           cursor.execute("""UPDATE dbo.Documentos_Normativos SET Estado=?,Reglamentacion_Detectada=?,
               Confianza_Global=?,Total_Hallazgos=?,Total_Propuestas=?,Total_Revisiones=?,Fecha_Analisis=sysdatetime()
               WHERE Documento_ID=?""", (state, result["regulation"], result["confidence"], result["total_findings"],
               result["total_proposals"], result["total_reviews"], document_id))
           connection.commit()
   except Exception as exc:
       with get_connection() as connection:
           cursor = connection.cursor()
           cursor.execute("UPDATE dbo.Documentos_Normativos SET Estado='ERROR',Error_Analisis=?,Fecha_Analisis=sysdatetime() WHERE Documento_ID=?", (str(exc)[:2000], document_id))
           connection.commit()
       raise HTTPException(status_code=422, detail=f"No se pudo analizar el documento: {exc}") from exc
   return document_detail(document_id, user)

@router.get("/documentos")
def documents(limit: int = 20, user: dict = Depends(require_role("CARGADOR"))):
   limit = max(1, min(limit, 100))
   return fetch_all(f"""SELECT TOP ({limit}) Documento_ID AS documento_id,Nombre_Archivo AS nombre_archivo,
       Estado AS estado,Reglamentacion_Detectada AS reglamentacion,Confianza_Global AS confianza,
       Total_Hallazgos AS total_hallazgos,Total_Propuestas AS total_propuestas,Total_Revisiones AS total_revisiones,
       Fecha_Carga AS fecha_carga,Carga_ID AS carga_id
       FROM dbo.Documentos_Normativos ORDER BY Documento_ID DESC""")

@router.get("/documentos/{document_id}")
def get_document(document_id: int, user: dict = Depends(require_role("CARGADOR"))):
   return document_detail(document_id, user)

@router.post("/documentos/{document_id}/crear-carga")
def create_load(document_id: int, payload: CreateLoadRequest, user: dict = Depends(require_role("CARGADOR"))):
   document = fetch_one("""SELECT Documento_ID AS documento_id,Nombre_Archivo AS nombre_archivo,Estado AS estado,
       Carga_ID AS carga_id FROM dbo.Documentos_Normativos WHERE Documento_ID=?""", (document_id,))
   if not document:
       raise HTTPException(status_code=404, detail="El documento no existe")
   if document["carga_id"]:
       raise HTTPException(status_code=409, detail=f"Este documento ya generó la carga #{document['carga_id']}")
   unique_ids = sorted(set(payload.hallazgo_ids))
   placeholders = ",".join("?" for _ in unique_ids)
   findings = fetch_all(f"""SELECT Hallazgo_ID AS hallazgo_id,Tipo_Registro_Propuesto AS tipo_registro,
       Datos_Propuestos_JSON AS datos_json FROM dbo.Documento_Hallazgos
       WHERE Documento_ID=? AND Hallazgo_ID IN ({placeholders}) AND Estado IN ('PROPUESTO','CONFIRMADO')
         AND Tipo_Registro_Propuesto IS NOT NULL AND Datos_Propuestos_JSON IS NOT NULL""", (document_id, *unique_ids))
   if len(findings) != len(unique_ids):
       raise HTTPException(status_code=422, detail="Algún hallazgo seleccionado no es una propuesta válida de este documento")
   refs = references()
   records = []
   for row_number, item in enumerate(findings, start=1):
       raw = json.loads(item["datos_json"])
       normalized, errors = normalize_record(item["tipo_registro"], raw, refs)
       records.append({"sheet": "Asistente automático", "row": row_number, "type": item["tipo_registro"], "normalized": normalized, "errors": errors})
   staged_products = refs["products"] | {item["normalized"]["data"].get("Codigo") for item in records if item["type"] == "PRODUCTO"}
   staged_organisms = refs["organisms"] | {item["normalized"]["data"].get("Codigo") for item in records if item["type"] == "ORGANISMO"}
   for item in records:
       data, errors = item["normalized"]["data"], item["errors"]
       if item["type"] == "EQUIVALENCIA":
           # En una BAJA no se envía Codigo_Consolidacion (no aplica cerrar sin ese dato);
           # sólo se valida el/los campos que la propuesta realmente trae.
           fields = ("Codigo_Desembolso",) if item["normalized"]["action"] == "BAJA" else ("Codigo_Desembolso", "Codigo_Consolidacion")
           for field in fields:
               if data.get(field) and data.get(field) not in staged_products:
                   errors.append((field, "PRODUCTO_INEXISTENTE", f"El producto {data.get(field)} no existe ni fue seleccionado para alta."))
       elif item["type"] == "ORGANISMO_TASA":
           if data.get("Codigo_Organismo") not in staged_organisms:
               errors.append(("Codigo_Organismo", "ORGANISMO_INEXISTENTE", "Seleccione también la propuesta de alta del organismo."))
           if data.get("Tasa_Pct") is not None:
               modality = f"TASA_{int(data['Tasa_Pct'] * 100):03d}"
               if ("802_01", modality) not in refs["modalities"]:
                   errors.append(("Tasa_Pct", "TASA_SIN_CUADRO", "No existe un cuadro 802_01 asociado a esta tasa."))
   load_id = persist_load("ASISTENTE", document["nombre_archivo"], None,
       f"Generada desde el documento analizado #{document_id}.", user, records, [])
   with get_connection() as connection:
       cursor = connection.cursor()
       cursor.execute("UPDATE dbo.Cargas_Normativas SET Documento_ID=? WHERE Carga_ID=?", (document_id, load_id))
       cursor.execute("UPDATE dbo.Documentos_Normativos SET Estado='CARGA_GENERADA',Carga_ID=? WHERE Documento_ID=? AND Carga_ID IS NULL", (load_id, document_id))
       cursor.execute(f"UPDATE dbo.Documento_Hallazgos SET Estado='INCLUIDO_CARGA',Seleccionado=1 WHERE Documento_ID=? AND Hallazgo_ID IN ({placeholders})", (document_id, *unique_ids))
       connection.commit()
   return load_detail(load_id, user)