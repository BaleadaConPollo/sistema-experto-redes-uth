"""
Motor de inferencia del Sistema Experto de Diagnóstico de Red.
UTH Campus Choluteca - IAE-0611 Inteligencia Artificial

Este módulo NO contiene ninguna regla de diagnóstico "quemada" en el código.
Es un intérprete genérico de árboles de decisión: lee la estructura completa
desde reglas_conocimiento.json y la recorre nodo por nodo. Esto significa que
un técnico de redes puede agregar, quitar o modificar reglas, preguntas,
severidades, SLA o soluciones editando SOLO el archivo JSON, sin tocar
ni una línea de este motor.

Los "sensores" (funciones que obtienen hechos reales del sistema operativo
o de la red) sí viven en código, porque requieren llamadas al sistema
(ping, sockets). El motor los invoca por nombre, según lo que diga el JSON.
"""

import csv
import json
import os
import platform
import re
import socket
import subprocess
from datetime import datetime


# ----------------------------------------------------------------------------
# Sensores: obtención de hechos reales (red / sistema operativo)
# ----------------------------------------------------------------------------

def _extraer_ipv4(texto: str):
    """Busca una dirección IPv4 dentro de un texto (ignora IPv6)."""
    coincidencia = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", texto)
    return coincidencia.group(0) if coincidencia else None


def detectar_gateway():
    """Detecta automáticamente el gateway de la conexión activa."""
    sistema = platform.system().lower()
    try:
        if sistema == "windows":
            salida = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=3).stdout
            lineas = salida.splitlines()
            for i, linea in enumerate(lineas):
                if "default gateway" in linea.lower() or "puerta de enlace predeterminada" in linea.lower():
                    candidato = _extraer_ipv4(linea)
                    if candidato:
                        return candidato
                    for siguiente in lineas[i + 1:i + 3]:
                        candidato = _extraer_ipv4(siguiente)
                        if candidato:
                            return candidato

        elif sistema == "darwin":
            salida = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=3).stdout
            for linea in salida.splitlines():
                if "gateway:" in linea:
                    return linea.split("gateway:")[1].strip()

        else:
            salida = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=3).stdout
            for linea in salida.splitlines():
                if linea.startswith("default via"):
                    return linea.split()[2]

    except (FileNotFoundError, subprocess.TimeoutExpired, IndexError):
        return None
    return None


def sensor_ping(destino: str, timeout_seg: int = 2) -> bool:
    """Ejecuta un ping real y regresa True si hubo respuesta."""
    flag_cantidad = "-n" if platform.system().lower() == "windows" else "-c"
    try:
        resultado = subprocess.run(
            ["ping", flag_cantidad, "1", str(destino)],
            capture_output=True, text=True, timeout=timeout_seg + 1,
        )
        return resultado.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def sensor_puerto(host: str, puerto, timeout_seg: float = 2.5) -> str:
    """Clasifica la respuesta de un socket TCP: activo_abierto / inactivo /
    bloqueado / host_invalido. Ver docstring detallado en versiones previas."""
    try:
        with socket.create_connection((host, int(puerto)), timeout=timeout_seg):
            return "activo_abierto"
    except ConnectionRefusedError:
        return "inactivo"
    except (socket.timeout, TimeoutError):
        return "bloqueado"
    except (socket.gaierror, ValueError, OSError):
        return "host_invalido"


# ----------------------------------------------------------------------------
# Motor de inferencia genérico
# ----------------------------------------------------------------------------

class MotorInferencia:
    """Intérprete genérico de árboles de decisión definidos en JSON."""

    SENSORES = {
        "ping": sensor_ping,
        "puerto": sensor_puerto,
    }

    def __init__(self, ruta_reglas: str = "reglas_conocimiento.json"):
        with open(ruta_reglas, encoding="utf-8") as archivo:
            self.reglas = json.load(archivo)

    def _resolver_parametros(self, parametros, contexto):
        """Reemplaza placeholders como '{host}' con valores del contexto
        (los datos concretos de la corrida actual: gateway detectado,
        host y puerto a probar, etc.)."""
        resueltos = []
        for p in parametros:
            if isinstance(p, str) and p.startswith("{") and p.endswith("}"):
                clave = p[1:-1]
                resueltos.append(contexto.get(clave, p))
            else:
                resueltos.append(p)
        return resueltos

    def ejecutar(self, arbol: str, contexto: dict, max_pasos: int = 20):
        """Recorre el árbol indicado ('diagnostico_local' o
        'diagnostico_remoto') usando los hechos disponibles en `contexto`.
        Regresa (nodo_resultado, ruta_evidencia, nodo_id_final):
          - nodo_resultado: el nodo hoja con el diagnóstico final.
          - ruta_evidencia: bitácora de cada pregunta evaluada y su respuesta
            (evidencia auditable para el reporte de incidente).
          - nodo_id_final: el id del nodo hoja alcanzado, útil para resaltar
            la ruta recorrida en visualizaciones."""
        nodo_id = self.reglas["arboles"][arbol]
        ruta_evidencia = []

        for _ in range(max_pasos):
            nodo = self.reglas["nodos"][nodo_id]

            if nodo["tipo"] == "resultado":
                return nodo, ruta_evidencia, nodo_id

            parametros = self._resolver_parametros(nodo.get("parametros", []), contexto)
            sensor_fn = self.SENSORES[nodo["sensor"]]
            resultado_sensor = sensor_fn(*parametros)

            ruta_evidencia.append({
                "nodo_id": nodo_id,
                "pregunta": nodo.get("pregunta", ""),
                "parametros": parametros,
                "resultado": resultado_sensor,
            })

            if nodo["tipo"] == "chequeo_booleano":
                nodo_id = nodo["si"] if resultado_sensor else nodo["no"]
            elif nodo["tipo"] == "chequeo_multivalor":
                nodo_id = nodo["ramas"].get(str(resultado_sensor), nodo["ramas"].get("default"))
            else:
                raise ValueError(f"Tipo de nodo desconocido en reglas_conocimiento.json: {nodo['tipo']}")

        raise RuntimeError(
            "El árbol de decisión excedió el número máximo de pasos. "
            "Revisa reglas_conocimiento.json: probablemente hay un ciclo entre nodos."
        )

    # ------------------------------------------------------------------
    # Bitácora / historial de diagnósticos (para auditoría empresarial)
    # ------------------------------------------------------------------
    @staticmethod
    def registrar_bitacora(ruta_csv: str, modo: str, objetivo: str, resultado: dict):
        existe = os.path.exists(ruta_csv)
        with open(ruta_csv, "a", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            if not existe:
                escritor.writerow(["fecha_hora", "modo", "objetivo", "regla", "diagnostico", "severidad"])
            escritor.writerow([
                datetime.now().isoformat(timespec="seconds"),
                modo, objetivo,
                resultado["regla"], resultado["diagnostico"], resultado["severidad"],
            ])
