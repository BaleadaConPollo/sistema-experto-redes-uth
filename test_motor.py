"""
Pruebas automatizadas del motor de inferencia — Sistema Experto de Diagnóstico de Red
UTH Campus Choluteca - IAE-0611 Inteligencia Artificial

Cómo correrlas:
    pip install pytest
    pytest test_motor.py -v

Cada prueba simula (mockea) los sensores de red para no depender de una
conexión real, y verifica que el motor dispare exactamente la regla
esperada — esto es la versión automatizada de la batería de casos de
prueba de la sección 5.4 de la rúbrica.
"""

import pytest
from motor_inferencia import MotorInferencia


@pytest.fixture
def motor():
    return MotorInferencia("reglas_conocimiento.json")


def test_r1_fallo_fisico_dhcp(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: False)
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "127.0.0.1", "puerto": 22})
    assert resultado["regla"] == "R1"
    assert resultado["diagnostico"] == "Fallo_Físico_o_DHCP"
    assert len(ruta) == 1  # se detuvo en el primer chequeo


def test_r2_fallo_enlace_wan(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: destino == "192.168.1.1")
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "127.0.0.1", "puerto": 22})
    assert resultado["diagnostico"] == "Fallo_Enlace_WAN"
    assert len(ruta) == 2


def test_r3_fallo_dns(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: destino != "google.com")
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "127.0.0.1", "puerto": 22})
    assert resultado["diagnostico"] == "Fallo_DNS"
    assert len(ruta) == 3


def test_r4_servicio_caido(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: True)
    monkeypatch.setitem(MotorInferencia.SENSORES, "puerto", lambda host, puerto, timeout_seg=2.5: "inactivo")
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "127.0.0.1", "puerto": 8080})
    assert resultado["diagnostico"] == "Servicio_Caído"
    assert resultado["severidad"] == "Alto"


def test_r5_bloqueo_firewall(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: True)
    monkeypatch.setitem(MotorInferencia.SENSORES, "puerto", lambda host, puerto, timeout_seg=2.5: "bloqueado")
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "127.0.0.1", "puerto": 8080})
    assert resultado["diagnostico"] == "Bloqueo_Firewall"
    assert resultado["severidad"] == "Medio"


def test_r6_conexion_ok(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: True)
    monkeypatch.setitem(MotorInferencia.SENSORES, "puerto", lambda host, puerto, timeout_seg=2.5: "activo_abierto")
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "127.0.0.1", "puerto": 8080})
    assert resultado["diagnostico"] == "Conexión_OK"
    assert resultado["severidad"] == "Informativo"


def test_r0_host_remoto_no_responde(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: False)
    resultado, ruta, _ = motor.ejecutar("diagnostico_remoto", {"host": "10.0.0.99", "puerto": 80})
    assert resultado["diagnostico"] == "Host_No_Responde"
    assert resultado["severidad"] == "Crítico"


def test_host_invalido_no_causa_excepcion(motor, monkeypatch):
    monkeypatch.setitem(MotorInferencia.SENSORES, "ping", lambda destino, timeout_seg=2: True)
    monkeypatch.setitem(MotorInferencia.SENSORES, "puerto", lambda host, puerto, timeout_seg=2.5: "host_invalido")
    resultado, ruta, _ = motor.ejecutar("diagnostico_local", {"gateway": "192.168.1.1", "host": "no-existe.invalido", "puerto": 80})
    assert resultado["diagnostico"] == "Host_Invalido"


def test_cobertura_de_reglas_completa(motor):
    """Confirma que las 6 reglas principales (R1-R6) existen en la base de
    conocimiento, como respaldo de la tabla de cobertura del documento de validación."""
    reglas_esperadas = {"R1", "R2", "R3", "R4", "R5", "R6"}
    reglas_presentes = {
        nodo["regla"] for nodo in motor.reglas["nodos"].values()
        if nodo["tipo"] == "resultado" and nodo["regla"] in reglas_esperadas
    }
    assert reglas_esperadas == reglas_presentes
