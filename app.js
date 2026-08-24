const API_URL = "http://127.0.0.1:8000/api";
const $ = id => document.getElementById(id);
const fields = {
  regulation: $("regulation"), date: $("agreement-date"), organism: $("organism"),
  province: $("province"), destination: $("destination"), user: $("user"),
  uva: $("uva"), modality: $("modality")
};
let regulations = new Map();
let organisms = new Map();

async function request(path, options = {}) {
  const headers = options.body instanceof FormData ? {} : {"Content-Type": "application/json"};
  const response = await fetch(API_URL + path, {headers, ...options});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Error HTTP ${response.status}`);
  }
  return response.json();
}

function query(values) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== "" && value != null) params.set(key, value); });
  return `?${params}`;
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c])); }
function fill(select, items, placeholder) { select.innerHTML = `<option value="">${placeholder}</option>` + items.map(item => `<option value="${escapeHtml(item.codigo)}">${escapeHtml(item.nombre)}</option>`).join(""); }
function reset(select, placeholder) { fill(select, [], placeholder); }
function show(id, visible = true) { $(id).hidden = !visible; }
function setEmpty() { $("result").innerHTML = '<div class="empty"><span>≡</span><h3>Completá la operación</h3><p>El resultado aparecerá cuando estén todos los datos.</p></div>'; }
function base() { return {reglamentacion: fields.regulation.value, fecha_acuerdo: fields.date.value, organismo: fields.organism.value, provincia: fields.province.value}; }

function clearOptions() {
  ["uva-wrap", "modality-wrap", "cap-wrap"].forEach(id => show(id, false));
  fields.uva.value = "";
  fields.modality.value = "";
  document.querySelectorAll('input[name="cap"]').forEach(item => { item.checked = false; });
}
function clearAfterProvince() {
  ["destination-wrap", "user-wrap"].forEach(id => show(id, false));
  reset(fields.destination, "Seleccionar destino");
  reset(fields.user, "Seleccionar usuario");
  clearOptions();
}
function clearAfterDestination() {
  show("user-wrap", false);
  reset(fields.user, "Seleccionar usuario");
  clearOptions();
}
function updateSubmit() {
  const regulation = fields.regulation.value;
  const dateOk = !regulations.get(regulation) || Boolean(fields.date.value);
  const organismOk = regulation !== "802_01" || Boolean(fields.organism.value);
  const required = regulation && organismOk && fields.province.value && fields.destination.value && fields.user.value && document.querySelector('input[name="cap"]:checked');
  const uvaOk = $("uva-wrap").hidden || fields.uva.value;
  const modalityOk = $("modality-wrap").hidden || fields.modality.value;
  $("submit").disabled = !(required && dateOk && uvaOk && modalityOk);
}

async function init() {
  try {
    const health = await request("/health");
    $("api-status").textContent = `Conectado · ${health.database_name}`;
    $("api-status").className = "status ok";
    const [regs, provinces] = await Promise.all([request("/reglamentaciones"), request("/provincias")]);
    regulations = new Map(regs.map(item => [item.codigo, Boolean(item.requiere_fecha)]));
    fill(fields.regulation, regs, "Seleccionar reglamentación");
    fill(fields.province, provinces, "Seleccionar provincia");
    initializeAdmin();
  } catch (error) {
    $("api-status").textContent = "API no disponible";
    $("api-status").className = "status error";
    fill(fields.regulation, [], "API no disponible");
    showError(error.message);
  }
}

fields.regulation.addEventListener("change", async () => {
  const regulation = fields.regulation.value;
  fields.date.value = "";
  fields.organism.value = "";
  fields.province.value = "";
  ["date-wrap", "organism-wrap", "province-wrap"].forEach(id => show(id, false));
  clearAfterProvince();
  $("organism-detail").textContent = "Seleccioná el organismo que liquida los haberes.";
  setEmpty();

  if (regulation === "802_01") {
    try {
      const items = await request("/organismos");
      organisms = new Map(items.map(item => [item.codigo, item]));
      fields.organism.innerHTML =
      '<option value="">Seleccionar organismo</option>' +
      items.map(item => `
      <option value="${escapeHtml(item.codigo)}">
          ${escapeHtml(item.nombre)}${item.vigente ? "" : " · FUERA DE VIGENCIA"}
      </option>
      `).join("");

      show("organism-wrap");
    } catch (error) { showError(error.message); }
  } else if (regulation && regulations.get(regulation)) {
    show("date-wrap");
  } else if (regulation) {
    show("province-wrap");
  }
  updateSubmit();
});

fields.date.addEventListener("change", () => {
  fields.province.value = "";
  clearAfterProvince();
  show("province-wrap", Boolean(fields.date.value));
  setEmpty();
  updateSubmit();
});

fields.organism.addEventListener("change", () => {
  fields.province.value = "";
  clearAfterProvince();
  show("province-wrap", Boolean(fields.organism.value));
  const item = organisms.get(fields.organism.value);
  if (item) {
    const second = item.tasa_segunda == null ? "sin segunda vivienda" : `2.ª vivienda ${Number(item.tasa_segunda).toFixed(2).replace(".", ",")}%`;
    const until = new Date(`${item.vigencia_hasta}T00:00:00`).toLocaleDateString("es-AR");
    $("organism-detail").textContent = `CUIT ${item.cuit} · 1.ª vivienda ${Number(item.tasa_primera).toFixed(2).replace(".", ",")}% · ${second} · Vigencia hasta ${until}`;
  }
  setEmpty();
  updateSubmit();
});

fields.province.addEventListener("change", async () => {
  clearAfterProvince();
  if (!fields.province.value) return updateSubmit();
  try {
    const items = await request("/destinos" + query(base()));
    fill(fields.destination, items, "Seleccionar destino");
    show("destination-wrap");
  } catch (error) { showError(error.message); }
  updateSubmit();
});

fields.destination.addEventListener("change", async () => {
  clearAfterDestination();
  if (!fields.destination.value) return updateSubmit();
  try {
    const items = await request("/usuarios" + query({...base(), destino: fields.destination.value}));
    fill(fields.user, items, "Seleccionar usuario");
    show("user-wrap");
  } catch (error) { showError(error.message); }
  updateSubmit();
});

fields.user.addEventListener("change", async () => {
  clearOptions(); // No reinicia fields.user: corrige el problema del selector que se vaciaba.
  if (!fields.user.value) return updateSubmit();
  try {
    const data = await request("/opciones" + query({...base(), destino: fields.destination.value, tipo_usuario: fields.user.value}));
    show("uva-wrap", Boolean(data.requiere_uva));
    if (fields.regulation.value !== "802_01" && data.modalidades.length) {
      fill(fields.modality, data.modalidades.map(item => ({codigo: item.codigo, nombre: `${item.nombre} (${Number(item.tasa).toFixed(2).replace(".", ",")}%)`})), "Seleccionar convenio");
      show("modality-wrap");
    }
    document.querySelectorAll('input[name="cap"]').forEach(radio => {
      radio.checked = false;
      radio.closest("label").hidden = (radio.value === "true" && !data.topeo_max) || (radio.value === "false" && data.topeo_min);
    });
    show("cap-wrap");
  } catch (error) { showError(error.message); }
  updateSubmit();
});

[fields.uva, fields.modality].forEach(element => element.addEventListener("input", updateSubmit));
document.querySelectorAll('input[name="cap"]').forEach(element => element.addEventListener("change", updateSubmit));

$("quote-form").addEventListener("submit", async event => {
  event.preventDefault();
  $("submit").disabled = true;
  $("submit").textContent = "Consultando…";
  try {
    const cap = document.querySelector('input[name="cap"]:checked').value === "true";
    const result = await request("/cotizar", {method: "POST", body: JSON.stringify({
      reglamentacion: fields.regulation.value,
      fecha_acuerdo: fields.date.value || null,
      organismo: fields.organism.value || null,
      provincia: fields.province.value,
      destino: fields.destination.value,
      tipo_usuario: fields.user.value,
      valor_vivienda_uva: fields.uva.value ? Number(fields.uva.value.replaceAll(".", "")) : null,
      modalidad_convenio: fields.modality.value || null,
      usa_topeo: cap
    })});
    renderResult(result);
  } catch (error) { showError(error.message); }
  finally { $("submit").textContent = "Consultar condición"; updateSubmit(); }
});

function product(label, code) { return code ? `<div class="product"><span>${label}</span><code>${escapeHtml(code)}</code><button type="button" data-code="${escapeHtml(code)}">Copiar</button></div>` : ""; }
function renderResult(data) {
  const organism = data.organismo_nombre ? `<div class="source"><strong>${escapeHtml(data.organismo_nombre)}</strong> · Vigencia hasta ${new Date(`${data.vigencia_hasta}T00:00:00`).toLocaleDateString("es-AR")}${data.organismo_vigente ? "" : " · VIGENCIA VENCIDA"}${data.adicional_topeo_pct != null ? ` · Adicional de topeo ${Number(data.adicional_topeo_pct).toFixed(2).replace(".", ",")}%` : ""}</div>` : "";
  $("result").innerHTML = `${organism}<div class="rate"><small>Tasa aplicable</small><strong>${Number(data.tasa_aplicable_pct).toFixed(2).replace(".", ",")}%</strong><small>Tasa nominal anual</small></div><div class="facts"><div><span>Permite topeo</span><b class="${data.permite_topeo ? "yes" : "no"}">${data.permite_topeo ? "SÍ" : "NO"}</b></div><div><span>Cobra prima</span><b class="${data.cobra_prima_topeo ? "yes" : "no"}">${data.cobra_prima_topeo ? "SÍ" : "NO"}</b></div></div><h3>Códigos de producto</h3>${product("Producto", data.codigo_producto)}${product("Desembolso", data.codigo_desembolso)}${product("Consolidación", data.codigo_consolidacion)}<div class="source">${escapeHtml(data.referencia_fuente)}${data.observaciones ? ` · ${escapeHtml(data.observaciones)}` : ""}</div>`;
  $("result").querySelectorAll("button[data-code]").forEach(button => button.addEventListener("click", () => { navigator.clipboard.writeText(button.dataset.code); button.textContent = "Copiado"; setTimeout(() => button.textContent = "Copiar", 1200); }));
}
function showError(message) { $("result").innerHTML = `<div class="alert"><strong>No se pudo obtener el resultado.</strong><br>${escapeHtml(message)}</div>`; }

function selectSection(section) {
  ["quote", "product", "admin"].forEach(name => {
    show(`${name}-section`, section === name);
    $(`${name}-tab`).classList.toggle("active", section === name);
  });
}
$("quote-tab").addEventListener("click", () => selectSection("quote"));
$("product-tab").addEventListener("click", () => selectSection("product"));
$("admin-tab").addEventListener("click", () => { selectSection("admin"); loadAdminLoads(); loadDocuments(); if(["APROBADOR","ADMINISTRADOR"].includes(adminProfile?.rol)){show("audit-panel");loadAudit()} });

$("disbursement-code").addEventListener("input", event => {
  event.target.value = event.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "");
});
$("product-form").addEventListener("submit", async event => {
  event.preventDefault();
  const code = $("disbursement-code").value.trim();
  if (!code) return;
  $("product-submit").disabled = true;
  $("product-submit").textContent = "Buscando…";
  try {
    const data = await request(`/consolidaciones/${encodeURIComponent(code)}`);
    $("product-result").innerHTML = `${product("Desembolso", data.codigo_desembolso)}${product("Consolidación", data.codigo_consolidacion)}<div class="source">Reglamentación ${escapeHtml(data.reglamentacion)}</div>`;
    $("product-result").querySelectorAll("button[data-code]").forEach(button => button.addEventListener("click", () => navigator.clipboard.writeText(button.dataset.code)));
  } catch (error) {
    $("product-result").innerHTML = `<div class="alert"><strong>No se encontró la conversión.</strong><br>${escapeHtml(error.message)}</div>`;
  } finally {
    $("product-submit").disabled = false;
    $("product-submit").textContent = "Buscar consolidación";
  }
});

let adminProfile = null;
const manualDefinitions = {
  PRODUCTO: [["Codigo","Código","text",true],["Activo","Activo","select",false]],
  EQUIVALENCIA: [["Codigo_Desembolso","Producto de desembolso","text",true],["Codigo_Consolidacion","Producto de consolidación","text",false],["Reglamentacion","Reglamentación","select-reg",true],["Fecha_Desde","Fecha desde","date",true],["Fecha_Hasta","Fecha hasta","date",false]],
  ORGANISMO: [["Codigo","Código","text",true],["Nombre","Nombre","text",false],["CUIT","CUIT","text",false],["Activo","Activo","select",false]],
  ORGANISMO_TASA: [["Codigo_Organismo","Código de organismo","text",true],["Tipo_Vivienda","Tipo de vivienda","select-dwelling",true],["Tasa_Pct","Tasa %","number",false],["Grupo_Pauta","Grupo de pauta","select-group",false],["Vigencia_Desde","Vigencia desde","date",true],["Vigencia_Hasta","Vigencia hasta","date",true],["Adicional_Topeo_Pct","Adicional topeo %","number",false],["Aplica_Circular_3214","Aplica Circular 3214","select",false],["Observaciones","Observaciones","text",false,"wide"]],
  CONDICION: [["Clave_Mantenimiento","Clave de mantenimiento","text",true],["Reglamentacion","Reglamentación","select-reg",false],["Ambito_Geografico","Ámbito geográfico","text",false],["Destino","Destino interno","text",false],["Tipo_Usuario","Tipo de usuario","text",false],["Modalidad_Convenio","Modalidad de convenio","text",false],["Fecha_Desde","Fecha desde","date",false],["Fecha_Hasta","Fecha hasta","date",false],["UVA_Desde","UVA desde","number",false],["UVA_Desde_Inclusive","Incluye UVA desde","select",false],["UVA_Hasta","UVA hasta","number",false],["UVA_Hasta_Inclusive","Incluye UVA hasta","select",false],["Tasa_Aplicable_Pct","Tasa aplicable %","number",false],["Permite_Topeo","Permite topeo","select",false],["Cobra_Prima_Topeo","Cobra prima","select",false],["Codigo_Producto","Producto único","text",false],["Codigo_Desembolso","Producto desembolso","text",false],["Codigo_Consolidacion","Producto consolidación","text",false],["Referencia_Fuente","Referencia normativa","text",false,"wide"],["Observaciones","Observaciones","text",false,"wide"]]
};

async function initializeAdmin() {
  try {
    adminProfile = await request("/admin/me");
    if (["CARGADOR","APROBADOR","ADMINISTRADOR"].includes(adminProfile.rol)) {
      show("admin-tab");
      $("admin-user").textContent = `${adminProfile.nombre} · ${adminProfile.rol}`;
      $("smart-effective-date").value = new Date().toISOString().slice(0,10);
      renderManualFields();
      if (adminProfile.rol === "ADMINISTRADOR") { show("users-panel"); loadPermissionUsers(); }
    }
  } catch (_) { show("admin-tab", false); }
}

function manualControl(field, label, type, required, extra) {
  const requiredMark = required ? " required" : "";
  let control;
  if (type === "select") control = `<select data-manual="${field}"${requiredMark}><option value="">Seleccionar</option><option value="SI">Sí</option><option value="NO">No</option></select>`;
  else if (type === "select-reg") control = `<select data-manual="${field}"${requiredMark}><option value="">Seleccionar</option><option value="800">800</option><option value="802">802</option><option value="802_01">802_01</option></select>`;
  else if (type === "select-dwelling") control = `<select data-manual="${field}"${requiredMark}><option value="">Seleccionar</option><option value="UNICA">Primera vivienda</option><option value="SEGUNDA">Segunda vivienda</option></select>`;
  else if (type === "select-group") control = `<select data-manual="${field}"${requiredMark}><option value="">Seleccionar</option><option value="PRE_3214">Anterior a Circular 3214</option><option value="POST_3214">Posterior a Circular 3214</option></select>`;
  else control = `<input data-manual="${field}" type="${type}"${type === "number" ? ' step="0.01"' : ""}${requiredMark}>`;
  return `<label class="${extra || ""}">${label}${control}</label>`;
}
function renderManualFields() {
  const definition = manualDefinitions[$("manual-type").value] || [];
  $("manual-fields").innerHTML = definition.map(item => manualControl(...item)).join("");
}
$("manual-type").addEventListener("change", renderManualFields);

$("smart-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = $("smart-file").files[0];
  if (!file || !$("smart-effective-date").value) return;
  const body = new FormData();
  body.append("file", file);
  body.append("fecha_desde", $("smart-effective-date").value);
  body.append("observaciones", $("smart-observations").value);
  $("smart-submit").disabled = true; $("smart-submit").textContent = "Analizando…";
  try {
    const data = await request("/admin/asistente/analizar", {method:"POST", body});
    renderDocument(data); await loadDocuments();
  } catch (error) { window.alert(error.message); }
  finally { $("smart-submit").disabled=false; $("smart-submit").textContent="Analizar documento"; }
});

async function loadDocuments() {
  if (!adminProfile) return;
  try {
    const rows = await request("/admin/asistente/documentos");
    $("documents-body").innerHTML = rows.length ? rows.map(item => `<tr data-document-id="${item.documento_id}"><td>#${item.documento_id}</td><td>${new Date(item.fecha_carga).toLocaleString("es-AR")}</td><td>${escapeHtml(item.nombre_archivo)}</td><td>${escapeHtml(item.reglamentacion||"—")}</td><td><span class="state-pill ${item.estado}">${escapeHtml(item.estado.replaceAll("_"," "))}</span></td><td>${item.total_propuestas}</td><td>${item.total_revisiones}</td><td>${item.carga_id?`#${item.carga_id}`:"—"}</td></tr>`).join("") : '<tr><td colspan="8">Todavía no hay documentos analizados.</td></tr>';
    $("documents-body").querySelectorAll("tr[data-document-id]").forEach(row => row.addEventListener("click", () => openDocument(Number(row.dataset.documentId))));
  } catch(error) { $("documents-body").innerHTML=`<tr><td colspan="8">${escapeHtml(error.message)}</td></tr>`; }
}

async function openDocument(id) {
  try { renderDocument(await request(`/admin/asistente/documentos/${id}`)); }
  catch(error) { window.alert(error.message); }
}

function renderDocument(data) {
  const selectable = data.hallazgos.filter(item => item.tipo_registro && ["PROPUESTO","CONFIRMADO"].includes(item.estado));
  const findings = data.hallazgos.map(item => {
    const canSelect = item.tipo_registro && ["PROPUESTO","CONFIRMADO"].includes(item.estado) && !data.carga_id;
    const checkbox = canSelect ? `<input type="checkbox" data-finding-id="${item.hallazgo_id}" ${item.seleccionado?"checked":""} aria-label="Incluir propuesta">` : '<span></span>';
    const proposed = item.datos_propuestos_json ? `<details><summary>Ver datos propuestos</summary><pre>${escapeHtml(prettyJson(item.datos_propuestos_json))}</pre></details>` : "";
    return `<article class="finding ${item.estado==="REQUIERE_REVISION"?"review":""}">${checkbox}<div class="finding-main"><h4>${escapeHtml(item.tipo.replaceAll("_"," "))}${item.tipo_registro?` · propuesta ${escapeHtml(item.tipo_registro.replaceAll("_"," "))}`:""}</h4><p>${escapeHtml(item.motivo||"")}</p><span class="finding-evidence"><strong>${escapeHtml(item.ubicacion||"Documento")}:</strong> ${escapeHtml(item.evidencia)}</span>${proposed}</div><div class="finding-confidence">${Number(item.confianza).toFixed(0)}%</div></article>`;
  }).join("");
  const actions = data.carga_id
    ? `<button class="primary" id="open-generated-load" type="button">Abrir carga #${data.carga_id}</button>`
    : selectable.length ? '<button class="secondary-button" id="select-proposals" type="button">Seleccionar todas</button><button class="primary" id="create-smart-load" type="button">Crear carga con seleccionadas</button><small>Solo se incluirán las casillas marcadas.</small>' : '<small>No hay propuestas publicables; revise los hallazgos o use la carga manual.</small>';
  $("smart-result").innerHTML = `<div class="smart-result-header"><div><span class="eyebrow">Resultado del análisis</span><h2>${escapeHtml(data.nombre_archivo)}</h2><p>Reglamentación ${escapeHtml(data.reglamentacion||"no detectada")} · Estado: ${escapeHtml(data.estado.replaceAll("_"," "))}</p></div><div class="confidence"><strong>${data.confianza==null?"—":`${Number(data.confianza).toFixed(0)}%`}</strong><small>confianza global</small></div></div><div class="smart-summary"><div class="summary-card"><small>Hallazgos</small><strong>${data.total_hallazgos}</strong></div><div class="summary-card"><small>Propuestas</small><strong>${data.total_propuestas}</strong></div><div class="summary-card"><small>Para revisar</small><strong>${data.total_revisiones}</strong></div><div class="summary-card"><small>Carga</small><strong>${data.carga_id?`#${data.carga_id}`:"—"}</strong></div></div>${data.error_analisis?`<div class="validation-item">${escapeHtml(data.error_analisis)}</div>`:""}<div class="smart-controls">${actions}</div><div class="findings">${findings||'<div class="admin-message">No se detectaron datos.</div>'}</div>`;
  show("smart-result"); $("smart-result").scrollIntoView({behavior:"smooth",block:"start"});
  if ($("select-proposals")) $("select-proposals").addEventListener("click", () => document.querySelectorAll("[data-finding-id]").forEach(item => {item.checked=true}));
  if ($("create-smart-load")) $("create-smart-load").addEventListener("click", () => createSmartLoad(data.documento_id));
  if ($("open-generated-load")) $("open-generated-load").addEventListener("click", () => openLoad(data.carga_id));
}

async function createSmartLoad(documentId) {
  const ids = [...document.querySelectorAll("[data-finding-id]:checked")].map(item => Number(item.dataset.findingId));
  if (!ids.length) { window.alert("Seleccioná al menos una propuesta."); return; }
  if (!window.confirm(`Se generará una carga validada con ${ids.length} propuestas. ¿Continuar?`)) return;
  $("create-smart-load").disabled=true; $("create-smart-load").textContent="Generando carga…";
  try {
    const load = await request(`/admin/asistente/documentos/${documentId}/crear-carga`, {method:"POST",body:JSON.stringify({hallazgo_ids:ids})});
    await Promise.all([loadAdminLoads(),loadDocuments()]); renderLoadDetail(load);
  } catch(error) { window.alert(error.message); $("create-smart-load").disabled=false; $("create-smart-load").textContent="Crear carga con seleccionadas"; }
}

$("upload-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = $("admin-file").files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  body.append("observaciones", $("upload-observations").value);
  $("upload-submit").disabled = true; $("upload-submit").textContent = "Validando…";
  try {
    const data = await request("/admin/cargas", {method:"POST", body});
    await loadAdminLoads(); renderLoadDetail(data);
  } catch (error) { window.alert(error.message); }
  finally { $("upload-submit").disabled=false; $("upload-submit").textContent="Validar archivo"; }
});

$("manual-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = {};
  document.querySelectorAll("[data-manual]").forEach(element => { data[element.dataset.manual] = element.value || null; });
  $("manual-submit").disabled=true; $("manual-submit").textContent="Validando…";
  try {
    const result = await request("/admin/cargas/manual", {method:"POST", body:JSON.stringify({tipo_registro:$("manual-type").value,accion:$("manual-action").value,datos:data,observaciones:$("manual-observations").value||null})});
    await loadAdminLoads(); renderLoadDetail(result); $("manual-form").reset(); renderManualFields();
  } catch(error) { window.alert(error.message); }
  finally { $("manual-submit").disabled=false; $("manual-submit").textContent="Crear carga validada"; }
});

async function loadAdminLoads() {
  if (!adminProfile) return;
  try {
    const rows=await request("/admin/cargas");
    $("loads-body").innerHTML=rows.length ? rows.map(row=>`<tr data-id="${row.carga_id}"><td>#${row.carga_id}</td><td>${new Date(row.fecha_carga).toLocaleString("es-AR")}</td><td>${escapeHtml(row.tipo_carga)}</td><td>${escapeHtml(row.usuario_carga)}</td><td><span class="state-pill ${row.estado}">${row.estado.replaceAll("_"," ")}</span></td><td>${row.total_altas}</td><td>${row.total_modificaciones}</td><td>${row.total_bajas}</td><td>${row.total_errores}</td></tr>`).join("") : '<tr><td colspan="9">Todavía no hay cargas.</td></tr>';
    $("loads-body").querySelectorAll("tr[data-id]").forEach(row=>row.addEventListener("click",()=>openLoad(Number(row.dataset.id))));
  } catch(error) { $("loads-body").innerHTML=`<tr><td colspan="9">${escapeHtml(error.message)}</td></tr>`; }
}
$("refresh-loads").addEventListener("click",loadAdminLoads);
async function openLoad(id){try{renderLoadDetail(await request(`/admin/cargas/${id}`));}catch(error){window.alert(error.message)}}
function prettyJson(value){if(!value)return "—";try{return JSON.stringify(JSON.parse(value),null,2)}catch(_){return value}}
function renderLoadDetail(data){
  const errors=data.errores.map(item=>`<div class="validation-item"><strong>${escapeHtml(item.severidad)}</strong> · ${escapeHtml(item.hoja||"")} ${item.fila?`fila ${item.fila}`:""}${item.campo?` · ${escapeHtml(item.campo)}`:""}<br>${escapeHtml(item.mensaje)}</div>`).join("");
  const rows=data.detalles.map(item=>`<tr><td>${escapeHtml(item.tipo_registro)}</td><td>${escapeHtml(item.clave)}</td><td><span class="state-pill ${item.accion_detectada}">${escapeHtml(item.accion_detectada||"ERROR")}</span></td><td><pre class="change-before">${escapeHtml(prettyJson(item.datos_anteriores_json))}</pre></td><td><pre class="change-after">${escapeHtml(prettyJson(item.datos_json))}</pre></td></tr>`).join("");
  const actions=`${data.puede_aprobar?'<button class="primary" id="approve-load" type="button">Aprobar carga</button>':""}${data.puede_publicar?'<button class="primary" id="publish-load" type="button">Publicar cambios</button>':""}${["VALIDADA","APROBADA"].includes(data.estado)&&["APROBADOR","ADMINISTRADOR"].includes(adminProfile.rol)?'<button class="secondary-button danger-button" id="reject-load" type="button">Rechazar</button>':""}`;
  $("load-detail").innerHTML=`<div class="title"><b>#</b><div><h2>Carga ${data.carga_id} · ${escapeHtml(data.estado)}</h2><p>${escapeHtml(data.nombre_archivo||"Cambio manual")} · cargada por ${escapeHtml(data.usuario_carga)}</p></div></div><div class="summary-cards"><div class="summary-card"><small>Registros</small><strong>${data.total_registros}</strong></div><div class="summary-card"><small>Altas</small><strong>${data.total_altas}</strong></div><div class="summary-card"><small>Modificaciones</small><strong>${data.total_modificaciones}</strong></div><div class="summary-card"><small>Bajas</small><strong>${data.total_bajas}</strong></div><div class="summary-card"><small>Errores</small><strong>${data.total_errores}</strong></div></div>${errors?`<div class="validation-list">${errors}</div>`:'<div class="admin-message">Validación completa: no se detectaron errores bloqueantes.</div>'}<div class="detail-actions">${actions}</div><div class="table-scroll"><table class="admin-table"><thead><tr><th>Tipo</th><th>Clave</th><th>Cambio</th><th>Antes</th><th>Después</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  show("load-detail"); $("load-detail").scrollIntoView({behavior:"smooth",block:"start"});
  if($("approve-load")) $("approve-load").addEventListener("click",()=>decideLoad(data.carga_id,"aprobar"));
  if($("publish-load")) $("publish-load").addEventListener("click",()=>publishLoad(data.carga_id));
  if($("reject-load")) $("reject-load").addEventListener("click",()=>decideLoad(data.carga_id,"rechazar"));
}
async function decideLoad(id,action){const observations=window.prompt(action==="rechazar"?"Motivo del rechazo (obligatorio):":"Observaciones de aprobación (opcional):")||"";if(action==="rechazar"&&!observations)return;try{await request(`/admin/cargas/${id}/${action}`,{method:"POST",body:JSON.stringify({observaciones:observations||null})});await loadAdminLoads();await openLoad(id)}catch(error){window.alert(error.message)}}
async function publishLoad(id){if(!window.confirm("¿Publicar esta carga? Los cambios quedarán disponibles en el cotizador y registrados en auditoría."))return;try{await request(`/admin/cargas/${id}/publicar`,{method:"POST"});await loadAdminLoads();await openLoad(id);window.alert("La carga se publicó correctamente.")}catch(error){window.alert(error.message)}}

async function loadPermissionUsers(){
  if(adminProfile?.rol!=="ADMINISTRADOR")return;
  try{const rows=await request("/admin/usuarios");$("users-body").innerHTML=rows.map(item=>`<tr><td>${escapeHtml(item.usuario)}</td><td>${escapeHtml(item.nombre||"—")}</td><td>${escapeHtml(item.rol)}</td><td>${item.activo?"Activo":"Inactivo"}</td></tr>`).join("");}catch(error){$("users-body").innerHTML=`<tr><td colspan="4">${escapeHtml(error.message)}</td></tr>`}
}
async function loadAudit(){try{const rows=await request("/admin/auditoria");$("audit-body").innerHTML=rows.length?rows.map(item=>`<tr><td>${new Date(item.fecha_cambio).toLocaleString("es-AR")}</td><td>#${item.carga_id}</td><td>${escapeHtml(item.tipo_registro)}</td><td>${escapeHtml(item.clave)}</td><td>${escapeHtml(item.accion)}</td><td>${escapeHtml(item.usuario)}</td></tr>`).join(""):'<tr><td colspan="6">Todavía no hay publicaciones.</td></tr>'}catch(error){$("audit-body").innerHTML=`<tr><td colspan="6">${escapeHtml(error.message)}</td></tr>`}}
$("user-form").addEventListener("submit",async event=>{event.preventDefault();try{await request("/admin/usuarios",{method:"POST",body:JSON.stringify({usuario:$("permission-user").value.trim(),nombre:$("permission-name").value.trim()||null,rol:$("permission-role").value,activo:$("permission-active").checked})});$("user-form").reset();$("permission-active").checked=true;await loadPermissionUsers()}catch(error){window.alert(error.message)}});

init();
