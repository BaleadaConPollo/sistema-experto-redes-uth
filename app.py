"""
Sistema Experto de Diagnóstico y Resolución de Fallas de Red — Edición Empresarial v3
UTH Campus Choluteca - IAE-0611 Inteligencia Artificial

Arquitectura:
  reglas_conocimiento.json  -> base de conocimiento (editable sin tocar código,
                               incluso desde la pestaña "Editor de reglas")
  motor_inferencia.py       -> motor genérico de inferencia + sensores de red
  test_motor.py             -> pruebas automatizadas (pytest) del motor
  app.py (este archivo)     -> interfaz: local, lotes en paralelo, dashboard,
                               editor de reglas, tickets ITSM, historial
"""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import streamlit as st

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    plt = None

from fpdf import FPDF, XPos, YPos

from motor_inferencia import MotorInferencia, detectar_gateway

RUTA_REGLAS = "reglas_conocimiento.json"
RUTA_BITACORA = "bitacora_diagnosticos.csv"
RUTA_AUTH = "auth_config.json"

st.set_page_config(page_title="Sistema Experto - Redes", page_icon="🌐", layout="centered")


# ----------------------------------------------------------------------------
# Autenticación básica
# ----------------------------------------------------------------------------

def _verificar_credenciales(usuario: str, clave: str) -> bool:
    if not os.path.exists(RUTA_AUTH):
        return True  # si no hay archivo de auth, no se bloquea el acceso
    with open(RUTA_AUTH, encoding="utf-8") as archivo:
        config_auth = json.load(archivo)
    clave_hash = hashlib.sha256(clave.encode("utf-8")).hexdigest()
    return usuario == config_auth.get("usuario") and clave_hash == config_auth.get("password_sha256")


if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🌐 Sistema Experto de Diagnóstico de Redes")
    st.caption("UTH Campus Choluteca · IAE-0611 Inteligencia Artificial")
    st.subheader("🔒 Inicia sesión para continuar")

    with st.form("form_login"):
        usuario_ingresado = st.text_input("Usuario")
        clave_ingresada = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        if _verificar_credenciales(usuario_ingresado, clave_ingresada):
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

    st.stop()  # detiene la ejecución del resto del script hasta autenticarse

# El motor se recarga en cada ejecución del script, así que cualquier cambio
# guardado desde la pestaña "Editor de reglas" se refleja de inmediato.
motor = MotorInferencia(RUTA_REGLAS)

with st.sidebar:
    st.write(f"👤 Sesión activa")
    if st.button("🚪 Cerrar sesión"):
        st.session_state.autenticado = False
        st.rerun()

COLOR_SEVERIDAD = {"Crítico": "🔴", "Alto": "🟠", "Medio": "🟡", "Informativo": "🟢"}
HEX_SEVERIDAD_BORDE = {"Crítico": "#A32D2D", "Alto": "#B5651D", "Medio": "#8A6D1D", "Informativo": "#3B6D11"}
HEX_SEVERIDAD_FONDO = {"Crítico": "#FCEBEB", "Alto": "#FCE8D5", "Medio": "#FFF3CD", "Informativo": "#EAF3DE"}
PRIORIDAD_ITSM = {"Crítico": "1 - Crítica", "Alto": "2 - Alta", "Medio": "3 - Media", "Informativo": "4 - Baja"}


# ----------------------------------------------------------------------------
# Utilidades de presentación
# ----------------------------------------------------------------------------

def mostrar_resultado(resultado: dict, ruta_evidencia: list):
    icono = COLOR_SEVERIDAD.get(resultado["severidad"], "⚪")
    if resultado["diagnostico"] == "Conexión_OK":
        st.success(f"{icono} **{resultado['titulo']}**  ·  Severidad: {resultado['severidad']}")
    else:
        st.error(f"{icono} **{resultado['titulo']}**  ·  Severidad: {resultado['severidad']}"
                 + (f"  ·  SLA: {resultado['sla_horas']} h" if resultado.get("sla_horas") else ""))
    st.markdown(resultado["solucion"])

    with st.expander("🔍 Ver ruta de evaluación (evidencia para el ticket)"):
        for paso in ruta_evidencia:
            st.write(f"- **{paso['pregunta']}** → parámetros: `{paso['parametros']}` → resultado: `{paso['resultado']}`")


def dibujar_ruta(ruta_evidencia: list, resultado: dict):
    """Dibuja la ruta exacta que recorrió el motor de inferencia en este
    diagnóstico, con el diagnóstico final resaltado según su severidad."""
    box_w, box_h, gap = 8.0, 1.5, 0.7
    total = len(ruta_evidencia) + 1
    alto_fig = total * (box_h + gap)

    fig, ax = plt.subplots(figsize=(6.5, max(2.2, alto_fig * 0.85)))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, alto_fig)
    ax.axis("off")

    y = alto_fig - box_h
    centros = []
    for paso in ruta_evidencia:
        rect = mpatches.FancyBboxPatch((1, y), box_w, box_h, boxstyle="round,pad=0.05,rounding_size=0.15",
                                        linewidth=1.4, edgecolor="#185FA5", facecolor="#E6F1FB")
        ax.add_patch(rect)
        texto = f"{paso['pregunta']}\nResultado: {paso['resultado']}"
        ax.text(1 + box_w / 2, y + box_h / 2, texto, ha="center", va="center", fontsize=8.5, color="#0C447C")
        centros.append((1 + box_w / 2, y, y + box_h))
        y -= (box_h + gap)

    borde = HEX_SEVERIDAD_BORDE.get(resultado["severidad"], "#444444")
    fondo = HEX_SEVERIDAD_FONDO.get(resultado["severidad"], "#EEEEEE")
    rect = mpatches.FancyBboxPatch((1, y), box_w, box_h, boxstyle="round,pad=0.05,rounding_size=0.15",
                                    linewidth=2.2, edgecolor=borde, facecolor=fondo)
    ax.add_patch(rect)
    ax.text(1 + box_w / 2, y + box_h / 2, f"{resultado['titulo']} ({resultado['regla']})",
            ha="center", va="center", fontsize=9.5, fontweight="bold", color=borde)
    centros.append((1 + box_w / 2, y, y + box_h))

    for i in range(len(centros) - 1):
        x0, y0_abajo, _ = centros[i]
        x1, _, y1_arriba = centros[i + 1]
        ax.annotate("", xy=(x1, y1_arriba), xytext=(x0, y0_abajo),
                    arrowprops=dict(arrowstyle="->", color="#444444", lw=1.3))

    fig.tight_layout()
    return fig


def generar_pdf_reporte(objetivo: str, resultado: dict, ruta_evidencia: list) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    ancho_util = pdf.w - pdf.l_margin - pdf.r_margin

    def _seguro(texto) -> str:
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    def titulo(texto, tam=16):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", tam)
        pdf.cell(ancho_util, 10, _seguro(texto), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def linea(texto, negrita=False, tam=11):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B" if negrita else "", tam)
        pdf.cell(ancho_util, 8, _seguro(texto), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def parrafo(texto, tam=11):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", tam)
        pdf.multi_cell(ancho_util, 7, _seguro(texto))

    titulo("Reporte de Diagnostico de Red")
    linea(f"Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    linea(f"Objetivo diagnosticado: {objetivo}")
    pdf.ln(4)

    linea(f"Diagnostico: {resultado['titulo']} ({resultado['regla']})", negrita=True, tam=13)
    linea("Severidad: " + resultado["severidad"]
          + (f"   |   SLA sugerido: {resultado['sla_horas']} horas" if resultado.get("sla_horas") else ""))
    pdf.ln(2)

    linea("Solucion recomendada:", negrita=True)
    parrafo(resultado["solucion"])
    pdf.ln(4)

    linea("Evidencia recolectada (ruta de evaluacion):", negrita=True)
    for i, paso in enumerate(ruta_evidencia, start=1):
        texto_paso = f"{i}. {paso['pregunta']} -> parametros {paso['parametros']} -> resultado: {paso['resultado']}"
        parrafo(texto_paso, tam=10)

    return bytes(pdf.output())


def generar_ticket_itsm(objetivo: str, resultado: dict) -> dict:
    """Genera un ticket en un formato compatible con el esquema típico de
    ServiceNow/Jira, para poder integrarse con una mesa de ayuda real."""
    return {
        "short_description": f"[{resultado['regla']}] {resultado['titulo']} - {objetivo}",
        "description": resultado["solucion"],
        "priority": PRIORIDAD_ITSM.get(resultado["severidad"], "4 - Baja"),
        "category": "Redes",
        "configuration_item": objetivo,
        "u_regla_sistema_experto": resultado["regla"],
        "u_diagnostico": resultado["diagnostico"],
        "u_severidad": resultado["severidad"],
        "u_sla_horas": resultado.get("sla_horas"),
        "fecha_deteccion": datetime.now().isoformat(timespec="seconds"),
    }


def enviar_alerta_webhook(url_webhook: str, objetivo: str, resultado: dict) -> tuple[bool, str]:
    """Envía una alerta a un webhook compatible con Slack/Discord (ambos
    aceptan el campo 'text' o 'content' con un mensaje simple). Se usa solo
    para severidad Crítico/Alto, simulando cómo un NOC real se entera de una
    falla sin estar viendo la pantalla. No lanza excepciones: si falla el
    envío (sin Internet, URL inválida), se reporta como advertencia, no error,
    para no interrumpir el diagnóstico."""
    if not url_webhook:
        return False, "No se configuró una URL de webhook."
    try:
        import requests
        mensaje = (
            f"🚨 *Alerta de red — {resultado['severidad']}*\n"
            f"Objetivo: {objetivo}\n"
            f"Diagnóstico: {resultado['titulo']} ({resultado['regla']})\n"
            f"SLA sugerido: {resultado['sla_horas']} horas\n"
            f"Solución: {resultado['solucion']}"
        )
        cuerpo = {"text": mensaje, "content": mensaje}  # compatible con Slack y Discord
        respuesta = requests.post(url_webhook, json=cuerpo, timeout=5)
        if respuesta.status_code in (200, 204):
            return True, "Alerta enviada correctamente."
        return False, f"El webhook respondió con estado {respuesta.status_code}."
    except Exception as error:
        return False, f"No se pudo enviar la alerta: {error}"


# ----------------------------------------------------------------------------
# Interfaz principal
# ----------------------------------------------------------------------------

st.title("🌐 Sistema Experto de Diagnóstico de Redes")
st.caption("UTH Campus Choluteca · IAE-0611 Inteligencia Artificial · Edición Empresarial")

tab_local, tab_lotes, tab_salud, tab_editor, tab_historial = st.tabs([
    "🖥️ Diagnóstico local", "🏢 Diagnóstico por lotes", "📊 Panel de salud",
    "⚙️ Editor de reglas", "📜 Historial y bitácora"
])

# ---------------- TAB 1: Diagnóstico local ----------------
with tab_local:
    st.subheader("Diagnóstico de este equipo")

    if "gateway_detectado" not in st.session_state:
        st.session_state.gateway_detectado = detectar_gateway()

    if st.session_state.gateway_detectado:
        st.success(f"🔎 Gateway detectado automáticamente: **{st.session_state.gateway_detectado}**")
        gateway_ip = st.session_state.gateway_detectado
        with st.expander("¿No es correcto? Ingrésalo manualmente"):
            gateway_ip = st.text_input("IP de tu gateway/router local", value=st.session_state.gateway_detectado)
    else:
        st.warning("⚠️ No se pudo detectar el gateway automáticamente. Ingrésalo manualmente:")
        gateway_ip = st.text_input("IP de tu gateway/router local", value="192.168.1.1")

    col1, col2 = st.columns(2)
    with col1:
        host_servicio = st.text_input("Host del servicio a probar (si la conectividad falla, no se llega a este paso)", value="127.0.0.1")
    with col2:
        puerto_servicio = st.number_input("Puerto", min_value=1, max_value=65535, value=22)

    if st.button("🚀 Ejecutar diagnóstico completo", key="btn_local"):
        contexto = {"gateway": gateway_ip, "host": host_servicio, "puerto": int(puerto_servicio)}
        with st.spinner("Recorriendo el árbol de decisión..."):
            resultado, ruta_evidencia, _ = motor.ejecutar("diagnostico_local", contexto)

        mostrar_resultado(resultado, ruta_evidencia)
        motor.registrar_bitacora(RUTA_BITACORA, "local", "Equipo local", resultado)

        if plt is not None:
            st.write("#### 🧭 Ruta recorrida por el motor de inferencia")
            st.pyplot(dibujar_ruta(ruta_evidencia, resultado))

        col_pdf, col_json = st.columns(2)
        with col_pdf:
            pdf_bytes = generar_pdf_reporte("Equipo local", resultado, ruta_evidencia)
            st.download_button("📄 Reporte de incidente (PDF)", data=pdf_bytes,
                                file_name=f"reporte_diagnostico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                mime="application/pdf")
        with col_json:
            ticket = generar_ticket_itsm("Equipo local", resultado)
            ticket_bytes = json.dumps(ticket, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button("🎫 Exportar como ticket ITSM (JSON)", data=ticket_bytes,
                                file_name=f"ticket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                mime="application/json")

        if resultado["severidad"] in ("Crítico", "Alto"):
            with st.expander("🔔 Enviar alerta automática (webhook Slack/Discord)"):
                url_webhook = st.text_input(
                    "URL del webhook (Slack Incoming Webhook o Discord Webhook)",
                    key="webhook_local",
                    placeholder="https://hooks.slack.com/services/...  ó  https://discord.com/api/webhooks/...",
                )
                if st.button("📨 Enviar alerta ahora", key="btn_webhook_local"):
                    exito, mensaje = enviar_alerta_webhook(url_webhook, "Equipo local", resultado)
                    (st.success if exito else st.warning)(mensaje)

# ---------------- TAB 2: Diagnóstico por lotes (empresarial, en paralelo) ----------------
with tab_lotes:
    st.subheader("Diagnóstico de múltiples equipos/servidores")
    st.caption("Corre en paralelo (varios hilos), como una herramienta de monitoreo de red real.")

    texto_lotes = st.text_area(
        "Un host por línea, formato `host:puerto` (si omites el puerto, se usa 80)",
        value="servidor-web:80\nservidor-bd:5432\n127.0.0.1:22",
        height=120,
    )

    if st.button("🚀 Ejecutar diagnóstico por lotes", key="btn_lotes"):
        entradas = []
        for linea in texto_lotes.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            if ":" in linea:
                host, _, puerto_txt = linea.partition(":")
                puerto = int(puerto_txt) if puerto_txt.strip().isdigit() else 80
            else:
                host, puerto = linea, 80
            entradas.append((host, puerto))

        resultados_por_host = {}
        with st.spinner(f"Diagnosticando {len(entradas)} equipos en paralelo..."):
            with ThreadPoolExecutor(max_workers=min(10, max(1, len(entradas)))) as executor:
                futuros = {
                    executor.submit(motor.ejecutar, "diagnostico_remoto", {"host": h, "puerto": p}): (h, p)
                    for h, p in entradas
                }
                for futuro in as_completed(futuros):
                    resultados_por_host[futuros[futuro]] = futuro.result()

        # Se registran en la bitácora de forma secuencial (fuera de los hilos)
        # para evitar escrituras simultáneas al mismo archivo CSV.
        filas = []
        for host, puerto in entradas:
            resultado, _ruta, _nodo_id = resultados_por_host[(host, puerto)]
            motor.registrar_bitacora(RUTA_BITACORA, "remoto", f"{host}:{puerto}", resultado)
            filas.append({
                "Host": host, "Puerto": puerto,
                "Estado": f"{COLOR_SEVERIDAD.get(resultado['severidad'], '⚪')} {resultado['titulo']}",
                "Regla": resultado["regla"], "Severidad": resultado["severidad"],
                "SLA (h)": resultado["sla_horas"] if resultado.get("sla_horas") else "—",
            })

        st.session_state["ultimo_lote"] = list(zip(entradas, [resultados_por_host[e][0] for e in entradas]))

        st.write("### Resumen del lote")
        if pd is not None:
            df = pd.DataFrame(filas)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("📄 Descargar resumen (CSV)", data=csv_bytes,
                                file_name=f"lote_diagnostico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv")
        else:
            st.table(filas)

        incidentes_graves = [
            (h, p, resultados_por_host[(h, p)][0]) for h, p in entradas
            if resultados_por_host[(h, p)][0]["severidad"] in ("Crítico", "Alto")
        ]
        if incidentes_graves:
            with st.expander(f"🔔 Enviar alerta automática de {len(incidentes_graves)} incidente(s) grave(s)"):
                url_webhook_lote = st.text_input(
                    "URL del webhook (Slack Incoming Webhook o Discord Webhook)",
                    key="webhook_lote",
                    placeholder="https://hooks.slack.com/services/...  ó  https://discord.com/api/webhooks/...",
                )
                if st.button("📨 Enviar todas las alertas", key="btn_webhook_lote"):
                    for host, puerto, resultado_grave in incidentes_graves:
                        exito, mensaje = enviar_alerta_webhook(url_webhook_lote, f"{host}:{puerto}", resultado_grave)
                        (st.success if exito else st.warning)(f"{host}:{puerto} → {mensaje}")

    if "ultimo_lote" in st.session_state:
        with st.expander("🎫 Exportar todo el lote como tickets ITSM (JSON)"):
            tickets = [generar_ticket_itsm(f"{h}:{p}", r) for (h, p), r in st.session_state["ultimo_lote"]]
            tickets_bytes = json.dumps(tickets, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button("Descargar tickets del último lote", data=tickets_bytes,
                                file_name=f"tickets_lote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                mime="application/json")

# ---------------- TAB 3: Panel de salud (dashboard) ----------------
with tab_salud:
    st.subheader("Panel de salud de red")

    if pd is not None and os.path.exists(RUTA_BITACORA):
        historial = pd.read_csv(RUTA_BITACORA)
        total = len(historial)
        sanos = int((historial["diagnostico"] == "Conexión_OK").sum())
        score = round(100 * sanos / total, 1) if total else 0.0

        col1, col2, col3 = st.columns(3)
        col1.metric("Puntaje de salud de red", f"{score}%")
        col2.metric("Diagnósticos totales", total)
        col3.metric("Incidentes críticos", int((historial["severidad"] == "Crítico").sum()))

        if plt is not None and total > 0:
            conteo = historial["severidad"].value_counts()
            colores = [HEX_SEVERIDAD_BORDE.get(s, "#999999") for s in conteo.index]
            fig, ax = plt.subplots(figsize=(4.5, 4.5))
            ax.pie(conteo.values, labels=conteo.index, autopct="%1.0f%%",
                   colors=colores, wedgeprops=dict(width=0.45), textprops={"fontsize": 9})
            ax.set_title("Distribución de severidad", fontsize=11)
            st.pyplot(fig)

        st.write("#### Diagnósticos más frecuentes")
        st.bar_chart(historial["diagnostico"].value_counts())
    else:
        st.info("Todavía no hay datos suficientes. Ejecuta un diagnóstico en las pestañas anteriores.")

# ---------------- TAB 4: Editor de reglas (sin tocar el JSON a mano) ----------------
with tab_editor:
    st.subheader("Editor de la base de conocimiento")
    st.caption("Edita severidad, SLA y solución de cada regla sin abrir el archivo JSON. Los cambios se guardan de inmediato.")

    ids_resultado = [nid for nid, n in motor.reglas["nodos"].items() if n["tipo"] == "resultado"]
    seleccion = st.selectbox(
        "Selecciona la regla a editar",
        ids_resultado,
        format_func=lambda nid: f"{motor.reglas['nodos'][nid]['regla']} — {motor.reglas['nodos'][nid]['titulo']}",
    )
    nodo = motor.reglas["nodos"][seleccion]
    opciones_severidad = ["Crítico", "Alto", "Medio", "Informativo"]

    with st.form("editor_regla"):
        nuevo_titulo = st.text_input("Título", value=nodo["titulo"])
        nueva_severidad = st.selectbox("Severidad", opciones_severidad, index=opciones_severidad.index(nodo["severidad"]))
        nuevo_sla = st.number_input("SLA en horas (0 = sin SLA / informativo)", min_value=0, value=int(nodo["sla_horas"] or 0))
        nueva_solucion = st.text_area("Solución recomendada", value=nodo["solucion"], height=150)
        guardar = st.form_submit_button("💾 Guardar cambios")

    if guardar:
        nodo["titulo"] = nuevo_titulo
        nodo["severidad"] = nueva_severidad
        nodo["sla_horas"] = nuevo_sla if nuevo_sla > 0 else None
        nodo["solucion"] = nueva_solucion
        with open(RUTA_REGLAS, "w", encoding="utf-8") as archivo:
            json.dump(motor.reglas, archivo, ensure_ascii=False, indent=2)
        st.success("✅ Regla actualizada. Los próximos diagnósticos ya usan este texto.")
        st.rerun()

# ---------------- TAB 5: Historial y bitácora ----------------
with tab_historial:
    st.subheader("Historial de diagnósticos")
    st.caption("Cada corrida (local o por lotes) queda registrada en bitacora_diagnosticos.csv, junto al proyecto.")

    if pd is not None:
        try:
            historial = pd.read_csv(RUTA_BITACORA)
            st.dataframe(historial, use_container_width=True, hide_index=True)
            st.write("#### Distribución de diagnósticos")
            st.bar_chart(historial["diagnostico"].value_counts())
        except FileNotFoundError:
            st.info("Todavía no hay diagnósticos registrados. Ejecuta uno en las pestañas anteriores.")
    else:
        st.warning("Instala pandas para ver el historial en tabla: `pip install pandas`")

st.divider()
with st.expander("📋 Ver la base de conocimiento completa (reglas_conocimiento.json)"):
    st.json(motor.reglas)
