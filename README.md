# 🌐 Sistema Experto de Diagnóstico y Resolución de Fallas de Red

[![Pruebas](https://img.shields.io/badge/pruebas-9%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![Licencia](https://img.shields.io/badge/uso-académico-lightgrey)]()

Proyecto final — **IAE-0611 Inteligencia Artificial**, UTH Campus Choluteca.
Catedrático: Henrry Javier Nuñez · Período II-2026.

Sistema Experto (Ruta B) que diagnostica fallas de conectividad de red mediante
un motor de inferencia genérico, con una base de conocimiento 100% externalizada
y editable, edición empresarial (lotes, dashboard, API, tickets ITSM) y
autenticación básica.

---

## 📐 Arquitectura

```
┌─────────────────────┐      ┌──────────────────────┐      ┌───────────────────────┐
│ reglas_conocimiento  │ ───▶ │  motor_inferencia.py  │ ───▶ │   app.py (Streamlit)   │
│      .json           │      │  (motor genérico +    │      │   api.py (FastAPI)     │
│ (base de conocimiento│      │   sensores de red)     │      │  (interfaces de uso)   │
│  editable sin código)│      │                        │      │                        │
└─────────────────────┘      └──────────────────────┘      └───────────────────────┘
                                        ▲
                                        │
                              test_motor.py (pytest)
                              9 pruebas automatizadas
```

**Principio de diseño clave:** `motor_inferencia.py` no contiene ninguna regla
de diagnóstico "quemada" en el código. Es un intérprete genérico de árboles de
decisión — lee la estructura completa desde `reglas_conocimiento.json` y la
recorre nodo por nodo. Un técnico de redes puede agregar, quitar o modificar
reglas, preguntas, severidades, SLA o soluciones editando **solo el JSON**
(o usando la pestaña "Editor de reglas" de la interfaz), sin tocar ni una
línea del motor.

---

## 📂 Estructura del repositorio

| Archivo | Rol |
|---|---|
| `reglas_conocimiento.json` | Base de conocimiento: árbol de decisión, reglas, severidad, SLA y soluciones |
| `motor_inferencia.py` | Motor de inferencia genérico + sensores de red (ping, chequeo de puerto, detección de gateway) |
| `app.py` | Interfaz Streamlit: diagnóstico local, lotes en paralelo, dashboard, editor de reglas, historial, login |
| `api.py` | API REST (FastAPI) que expone el motor como servicio web |
| `test_motor.py` | Suite de pruebas automatizadas (pytest) — 9 pruebas, una por regla |
| `auth_config.json` | Credenciales de acceso al panel (usuario + hash de contraseña) |
| `Dockerfile` / `.dockerignore` | Empaquetado para despliegue en un contenedor |
| `.github/workflows/tests.yml` | CI: corre las pruebas automáticamente en cada cambio |
| `requirements.txt` | Dependencias de Python |

---

## 🚀 Instalación y ejecución

### Opción 1 — Local con Python

```bash
pip install -r requirements.txt
streamlit run app.py
```

Abre `http://localhost:8501`. Usuario por defecto: `admin` / contraseña: `uth2026`
(cámbiala en `auth_config.json` antes de la demo — ver instrucciones dentro del archivo).

### Opción 2 — API REST

```bash
uvicorn api:app --reload --port 8000
```

Documentación interactiva (Swagger UI): `http://localhost:8000/docs`

### Opción 3 — Docker

```bash
docker build -t sistema-experto-redes .
docker run -p 8501:8501 sistema-experto-redes
```

### Pruebas automatizadas

```bash
pytest test_motor.py -v
```

---

## 🧠 Base de conocimiento (resumen)

| Regla | Diagnóstico | Severidad | SLA |
|---|---|---|---|
| R1 | Fallo físico / DHCP | 🔴 Crítico | 1 h |
| R2 | Fallo de enlace WAN | 🔴 Crítico | 2 h |
| R3 | Fallo de DNS | 🟠 Alto | 4 h |
| R4 | Servicio caído | 🟠 Alto | 4 h |
| R5 | Bloqueo de firewall | 🟡 Medio | 8 h |
| R6 | Conexión funcionando correctamente | 🟢 Informativo | — |
| R0 | Host remoto sin respuesta (modo lotes) | 🔴 Crítico | 1 h |

Detalle completo, preguntas y soluciones: ver `reglas_conocimiento.json` o la
pestaña "Editor de reglas" de la aplicación.

---

## ✨ Funcionalidades

- **Diagnóstico local** — detecta automáticamente el gateway y recorre el árbol de decisión completo (conectividad → WAN → DNS → servicio/firewall).
- **Diagnóstico por lotes** — revisa varios servidores a la vez, en paralelo (`ThreadPoolExecutor`).
- **Panel de salud** — puntaje de red, conteo de incidentes críticos y distribución de severidad.
- **Editor de reglas** — modifica severidad, SLA y soluciones desde la interfaz, sin tocar el JSON a mano.
- **Historial y bitácora** — cada diagnóstico queda registrado en `bitacora_diagnosticos.csv`.
- **Reportes PDF** — genera un reporte de incidente descargable con evidencia paso a paso.
- **Tickets ITSM** — exporta el diagnóstico en formato JSON compatible con ServiceNow/Jira.
- **Alertas webhook** — notifica incidentes Crítico/Alto a Slack o Discord.
- **API REST** — expone el motor para integrarse con otros sistemas.
- **Autenticación básica** — protege el acceso al panel.

---

## 👥 Autores

Proyecto desarrollado por el grupo de IAE-0611, UTH Campus Choluteca, II período 2026.

*(Completar con los nombres de los integrantes antes de la entrega final.)*
