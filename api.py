"""
API REST del Sistema Experto de Diagnóstico de Red — Edición Empresarial
UTH Campus Choluteca - IAE-0611 Inteligencia Artificial

Expone el mismo motor de inferencia usado por app.py como un servicio web,
para que otros sistemas (una mesa de ayuda, un script de monitoreo, otro
backend) puedan consultarlo sin depender de la interfaz de Streamlit.

Cómo correrla:
    pip install fastapi uvicorn
    uvicorn api:app --reload --port 8000

Documentación interactiva automática (Swagger UI) una vez corriendo:
    http://localhost:8000/docs
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from motor_inferencia import MotorInferencia, detectar_gateway

app = FastAPI(
    title="Sistema Experto de Diagnóstico de Redes — API",
    description="Servicio web del motor de inferencia. UTH Campus Choluteca - IAE-0611.",
    version="1.0.0",
)

motor = MotorInferencia("reglas_conocimiento.json")


# ----------------------------------------------------------------------------
# Esquemas de entrada/salida (Pydantic)
# ----------------------------------------------------------------------------

class SolicitudDiagnosticoLocal(BaseModel):
    gateway: Optional[str] = Field(None, description="IP del gateway. Si se omite, se autodetecta.")
    host: str = Field("127.0.0.1", description="Host del servicio a probar")
    puerto: int = Field(22, ge=1, le=65535, description="Puerto del servicio a probar")


class SolicitudDiagnosticoRemoto(BaseModel):
    host: str = Field(..., description="Host o IP del equipo remoto a diagnosticar")
    puerto: int = Field(80, ge=1, le=65535, description="Puerto del servicio a probar")


class PasoEvidencia(BaseModel):
    nodo_id: str
    pregunta: str
    parametros: list
    resultado: str | bool


class RespuestaDiagnostico(BaseModel):
    regla: str
    diagnostico: str
    titulo: str
    severidad: str
    sla_horas: Optional[int]
    solucion: str
    ruta_evidencia: list[PasoEvidencia]


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------

@app.get("/health", tags=["Estado"])
def salud():
    """Chequeo simple de que la API está viva (usado por balanceadores de carga / monitoreo)."""
    return {"estado": "ok", "servicio": "sistema-experto-redes"}


@app.get("/reglas", tags=["Base de conocimiento"])
def obtener_reglas():
    """Regresa la base de conocimiento completa (útil para auditoría externa)."""
    return motor.reglas


@app.post("/diagnosticar/local", response_model=RespuestaDiagnostico, tags=["Diagnóstico"])
def diagnosticar_local(solicitud: SolicitudDiagnosticoLocal):
    """Ejecuta el árbol de diagnóstico completo (gateway -> WAN -> DNS -> servicio/firewall)
    sobre el equipo donde corre esta API."""
    gateway = solicitud.gateway or detectar_gateway()
    if not gateway:
        raise HTTPException(status_code=422, detail="No se pudo detectar el gateway; envíalo explícitamente en 'gateway'.")

    contexto = {"gateway": gateway, "host": solicitud.host, "puerto": solicitud.puerto}
    resultado, ruta_evidencia, _nodo_id = motor.ejecutar("diagnostico_local", contexto)
    motor.registrar_bitacora("bitacora_diagnosticos.csv", "api_local", solicitud.host, resultado)

    return {**resultado, "ruta_evidencia": ruta_evidencia}


@app.post("/diagnosticar/remoto", response_model=RespuestaDiagnostico, tags=["Diagnóstico"])
def diagnosticar_remoto(solicitud: SolicitudDiagnosticoRemoto):
    """Diagnostica un host remoto (ping + chequeo de puerto), ideal para integrarse
    con un sistema de monitoreo que revisa muchos servidores."""
    contexto = {"host": solicitud.host, "puerto": solicitud.puerto}
    resultado, ruta_evidencia, _nodo_id = motor.ejecutar("diagnostico_remoto", contexto)
    motor.registrar_bitacora("bitacora_diagnosticos.csv", "api_remoto", f"{solicitud.host}:{solicitud.puerto}", resultado)

    return {**resultado, "ruta_evidencia": ruta_evidencia}
