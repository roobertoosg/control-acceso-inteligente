"""
Punto de Entrada Principal (Main Loop y Orquestador).
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Optional, Tuple

from .access_logic import decidir_evento
from .anomaly_logic import (
    evaluar_denegacion,
    evaluar_evento_permitido_completado,
)
from .config import Config
from .db import Database
from .serial_manager import SerialManager
from .utils import log


# Volvemos a solo 2 datos, porque el alcohol se manejará como un evento separado
UidEvent = Tuple[str, str]      
DeviceEvent = Tuple[str, dict]  # (event_type, {'alcohol': 150, 'temp': 36.5}) o (event_type, raw_message)

def normalizar_uid(uid: str) -> str:
    return (uid or "").strip().upper()


def vaciar_cola(q: queue.Queue) -> None:
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        pass


def wait_for_queue_event(
    event_queue: queue.Queue,
    expected_type: str,
    timeout_seconds: int,
) -> str | None:
    """
    Espera activamente en la cola por un evento. 
    Retorna el valor del evento si lo encuentra, o None si hay timeout.
    """
    limite = time.time() + timeout_seconds

    while time.time() < limite:
        restante = max(0.1, limite - time.time())
        try:
            event_type, raw = event_queue.get(timeout=min(0.3, restante))
        except queue.Empty:
            continue

        log(f"[QUEUE-EVENT] {event_type} -> {raw}")

        if event_type == expected_type:
            return raw

    return None


def procesar_uid(
    db: Database,
    serial_mgr: Optional[SerialManager],
    punto: dict,
    event_queue: queue.Queue,
    uid: str,
    source: str,
) -> None:
    
    uid = normalizar_uid(uid)

    if not uid:
        return

    event_dt = datetime.now().astimezone()
    usuario = db.get_usuario_by_uid(uid)
    decision = decidir_evento(usuario)

    log(f"UID recibido desde [{source}]: {uid}")

    if usuario:
        nombre_completo = " ".join(
            x for x in [
                usuario.get("nombre"),
                usuario.get("apellido_paterno"),
                usuario.get("apellido_materno"),
            ] if x
        )
        log(f"Usuario: {nombre_completo} | Estado actual: {usuario.get('estado_actual')}")
    else:
        log("Usuario no encontrado")

    nivel_alcohol = 0
    temperatura = 36.5 # Inicialización segura por si es manual

    # ------------------------------------------------------
    # LÓGICA DE SALUD (ALCOHOL + TEMPERATURA) SOLO EN ENTRADA
    # ------------------------------------------------------
    if decision["permitido"] and decision["modo_evento"] == "ENTRADA":
        log("💳 Tarjeta de ENTRADA detectada.")
        if serial_mgr is not None:
            vaciar_cola(event_queue)
            
            serial_mgr.send_command("CMD:SOPLAR")
            log("⏳ Por favor, acérquese al sensor y sople durante 10 segundos...")

            # Esperamos hasta 12 segundos por el paquete de salud del Arduino
            datos_salud = wait_for_queue_event(
                event_queue=event_queue,
                expected_type="salud",
                timeout_seconds=12, 
            )

            if datos_salud is None:
                log("❌ Error: No se recibieron datos de los sensores de salud.")
                decision["permitido"] = False
                decision["resultado"] = "INCOMPLETO"
                decision["motivo_codigo"] = "EVENTO_INCOMPLETO_TIMEOUT"
                decision["detalle"] = "Fallo al leer sensores de salud"
            else:
                # Extraemos los datos del diccionario
                nivel_alcohol = datos_salud.get('alcohol', 0)
                temperatura = datos_salud.get('temp', 0.0)
                
                log(f"🩺 Muestras capturadas -> Alcohol: {nivel_alcohol} | Temp: {temperatura}°C")
                time.sleep(2) 
                
                # --- REGLAS DE SALUD (El Árbitro) ---
                if nivel_alcohol >= Config.ALCOHOL_MAX_PERMITIDO:
                    log(f"ALERTA ROJA: Nivel de alcohol ({nivel_alcohol}) supera el límite. Bloqueando.")
                    decision["permitido"] = False
                    decision["resultado"] = "DENEGADO"
                    decision["motivo_codigo"] = "ALCOHOLIMETRO_POSITIVO"
                    decision["detalle"] = f"Alcohol detectado: {nivel_alcohol}"
                    
                elif temperatura >= Config.TEMP_FIEBRE:
                    log(f"ALERTA ROJA: Fiebre detectada ({temperatura}°C). Bloqueando por seguridad sanitaria.")
                    decision["permitido"] = False
                    decision["resultado"] = "DENEGADO"
                    decision["motivo_codigo"] = "TEMPERATURA_ALTA"
                    decision["detalle"] = f"Temperatura alta: {temperatura}°C"
                    
                elif temperatura < Config.TEMP_MIN_VALIDA:
                    log(f"⚠️ Lectura de temperatura inválida ({temperatura}°C). Posible mala posición.")
                    decision["permitido"] = False
                    decision["resultado"] = "INCOMPLETO"
                    decision["motivo_codigo"] = "TEMPERATURA_INVALIDA"
                    decision["detalle"] = "Favor de acercarse al sensor y repetir la prueba."
                    
                else:
                    log(f"✅ Estado de salud verificado. Autorizando acceso...")

    # ------------------------------------------------------
    # CASO: ACCESO DENEGADO
    # ------------------------------------------------------
    if not decision["permitido"]:
        log("Acceso denegado")

        analisis_denegacion = evaluar_denegacion(
            db=db,
            uid_rfid=uid,
            usuario=usuario,
            decision=decision,
            event_dt=event_dt,
        )

        motivo = db.get_motivo_by_codigo(analisis_denegacion["motivo_codigo"])

        if serial_mgr is not None:
            # Traducimos el motivo complejo de la BD a un comando corto para el Arduino
            motivo_cod = analisis_denegacion["motivo_codigo"]
            cmd_denegar = "CMD:DENEGAR:GENERICO"
            
            if motivo_cod == "ALCOHOLIMETRO_POSITIVO":
                cmd_denegar = "CMD:DENEGAR:ALCOHOL"
            elif motivo_cod == "TEMPERATURA_ALTA":
                cmd_denegar = "CMD:DENEGAR:FIEBRE"
            elif motivo_cod == "TEMPERATURA_INVALIDA":
                cmd_denegar = "CMD:DENEGAR:MALATEMP"
            elif motivo_cod == "USUARIO_NO_ENCONTRADO" or not usuario:
                cmd_denegar = "CMD:DENEGAR:NO_REG"
            elif "HORARIO" in motivo_cod or "CLASE" in motivo_cod:
                cmd_denegar = "CMD:DENEGAR:HORARIO"

            try:
                serial_mgr.send_command(cmd_denegar)
            except Exception as exc:
                log(f"No se pudo enviar {cmd_denegar}: {exc}")

        detalle = decision["detalle"]
        if analisis_denegacion["detalle_extra"]:
            detalle = f"{detalle} | {analisis_denegacion['detalle_extra']}"      
        # --- NUEVO: Agregar evidencia de salud al log ---
        if decision["modo_evento"] == "ENTRADA" and nivel_alcohol > 0:
            detalle = f"{detalle} | Alc:{nivel_alcohol} Temp:{temperatura}°C"
        detalle = f"{detalle} | source={source}"

        db.insert_evento(
            id_usuario=usuario["id_usuario"] if usuario else None,
            uid_rfid_leido=uid,
            id_punto=punto["id_punto"],
            modo_evento=decision["modo_evento"],
            resultado=analisis_denegacion["resultado"],
            id_motivo=motivo["id_motivo"],
            estado_anterior=decision["estado_anterior"],
            estado_nuevo=decision["estado_nuevo"],
            paso_detectado=False,
            servo_activado=False,
            anomalia_score=analisis_denegacion["anomalia_score"],
            detalle=detalle,
        )
        db.commit()

        if analisis_denegacion["es_anomalia"]:
            log(f"Denegación ANOMALIA | motivo={analisis_denegacion['motivo_codigo']} | score={analisis_denegacion['anomalia_score']}")
        else:
            log("Evento denegado registrado en BD")
        return

    # ------------------------------------------------------
    # CASO: ACCESO PERMITIDO
    # ------------------------------------------------------
    log(f"{decision['detalle']} -> enviando CMD:PERMITIR")

    paso_ok = False
    servo_activado = serial_mgr is not None

    if serial_mgr is not None:
        vaciar_cola(event_queue)

        try:
            # Le avisamos al Arduino si es Entrada o Salida para el mensaje
            tipo_acceso = "ENTRADA" if decision["modo_evento"] == "ENTRADA" else "SALIDA"
            serial_mgr.send_command(f"CMD:PERMITIR:{tipo_acceso}")
        except Exception as exc:
            raise RuntimeError(f"No se pudo enviar CMD:PERMITIR: {exc}") from exc

        raw_paso = wait_for_queue_event(
            event_queue=event_queue,
            expected_type="paso",
            timeout_seconds=Config.PASO_TIMEOUT,
        )
        paso_ok = bool(raw_paso)
    else:
        log("Modo sin serial activo: simulando paso detectado")
        paso_ok = True
        servo_activado = False

    # ------------------------------------------------------
    # CASO: EVENTO INCOMPLETO
    # ------------------------------------------------------
    if not paso_ok:
        log("No hubo paso detectado dentro del tiempo límite")
        motivo_timeout = db.get_motivo_by_codigo("EVENTO_INCOMPLETO_TIMEOUT")

        db.insert_evento(
            id_usuario=usuario["id_usuario"],
            uid_rfid_leido=uid,
            id_punto=punto["id_punto"],
            modo_evento=decision["modo_evento"],
            resultado="INCOMPLETO",
            id_motivo=motivo_timeout["id_motivo"],
            estado_anterior=decision["estado_anterior"],
            estado_nuevo=decision["estado_anterior"],
            paso_detectado=False,
            servo_activado=servo_activado,
            anomalia_score=0,
            detalle=f"Se autorizó el acceso, pero no se detectó paso | source={source}",
        )
        db.commit()

        if serial_mgr is not None:
            try:
                serial_mgr.send_command("CMD:CERRAR")
            except Exception as exc:
                log(f"No se pudo enviar CMD:CERRAR tras timeout: {exc}")

        return

    # ------------------------------------------------------
    # CASO: PASO DETECTADO -> EVALUAR ANOMALÍAS
    # ------------------------------------------------------
    log("Paso detectado, evaluando anomalías del acceso completado")

    analisis = evaluar_evento_permitido_completado(
        db=db,
        usuario=usuario,
        decision=decision,
        event_dt=event_dt,
    )

# REGLA SALUD: ADVERTENCIAS (Residual o Febrícula) solo si fue ENTRADA
    if decision["modo_evento"] == "ENTRADA":
        if Config.ALCOHOL_ADVERTENCIA <= nivel_alcohol < Config.ALCOHOL_MAX_PERMITIDO:
            analisis["es_anomalia"] = True
            analisis["resultado"] = "ANOMALIA"
            analisis["motivo_codigo"] = "ALCOHOLIMETRO_ADVERTENCIA"
            analisis["anomalia_score"] = max(analisis.get("anomalia_score", 0), 50)
            analisis["detalle_extra"] = f"Aliento residual detectado: {nivel_alcohol}"
            
        elif Config.TEMP_MAX_NORMAL < temperatura < Config.TEMP_FIEBRE:
            analisis["es_anomalia"] = True
            analisis["resultado"] = "ANOMALIA"
            analisis["motivo_codigo"] = "TEMPERATURA_ADVERTENCIA"
            analisis["anomalia_score"] = max(analisis.get("anomalia_score", 0), 40)
            analisis["detalle_extra"] = f"Febrícula detectada: {temperatura}°C"

    motivo_final = db.get_motivo_by_codigo(analisis["motivo_codigo"])

    detalle_final = decision["detalle"]
    if analisis["detalle_extra"]:
        detalle_final = f"{detalle_final} | {analisis['detalle_extra']}"
    # --- NUEVO: Agregar evidencia de salud al log ---
    if decision["modo_evento"] == "ENTRADA" and nivel_alcohol > 0:
        # Solo lo agregamos si no se agregó ya como anomalía (para no repetir)
        if "Alc:" not in detalle_final and "Temp:" not in detalle_final:
            detalle_final = f"{detalle_final} | Alc:{nivel_alcohol} Temp:{temperatura}°C"          
    detalle_final = f"{detalle_final} | source={source}"

    db.insert_evento(
        id_usuario=usuario["id_usuario"],
        uid_rfid_leido=uid,
        id_punto=punto["id_punto"],
        modo_evento=decision["modo_evento"],
        resultado=analisis["resultado"],
        id_motivo=motivo_final["id_motivo"],
        estado_anterior=decision["estado_anterior"],
        estado_nuevo=decision["estado_nuevo"],
        paso_detectado=True,
        servo_activado=servo_activado,
        anomalia_score=analisis["anomalia_score"],
        detalle=detalle_final,
    )

    db.update_estado_usuario(usuario["id_usuario"], decision["estado_nuevo"])
    db.commit()

    if analisis["es_anomalia"]:
        log(f"Evento registrado como ANOMALIA | motivo={analisis['motivo_codigo']} | score={analisis['anomalia_score']}")
    else:
        log(f"Evento registrado. Nuevo estado del usuario: {decision['estado_nuevo']}")

    if serial_mgr is not None:
        try:
            serial_mgr.send_command("CMD:CERRAR")
        except Exception as exc:
            pass


def serial_listener(
    serial_mgr: SerialManager,
    uid_queue: queue.Queue,
    event_queue: queue.Queue,
    stop_event: threading.Event,
) -> None:
    log("Hilo serial activo, esperando mensajes...")
    
    # Variables temporales para agrupar los datos de salud
    temp_alcohol = None
    temp_temperatura = None

    while not stop_event.is_set():
        try:
            msg = serial_mgr.read_line()
            if not msg:
                continue
            
            msg = msg.strip()
            if "PONG" not in msg and "MUESTREANDO" not in msg:
                log(f"[SERIAL] {msg}")

            if msg.startswith("EVENTO:RFID:"):
                uid = normalizar_uid(msg.replace("EVENTO:RFID:", "", 1))
                if uid:
                    uid_queue.put(("rfid", uid))

            # ATRAPAMOS EL ALCOHOL (Y LO GUARDAMOS TEMPORALMENTE)
            elif msg.startswith("EVENTO:ALCOHOL:"):
                temp_alcohol = int(msg.replace("EVENTO:ALCOHOL:", "").strip())

            # ATRAPAMOS LA TEMPERATURA Y MANDAMOS EL PAQUETE COMPLETO
            elif msg.startswith("EVENTO:TEMP:"):
                temp_temperatura = float(msg.replace("EVENTO:TEMP:", "").strip())
                
                # Solo si ya leímos el alcohol milisegundos antes, armamos el paquete
                if temp_alcohol is not None:
                    paquete_salud = {
                        'alcohol': temp_alcohol,
                        'temp': temp_temperatura
                    }
                    event_queue.put(("salud", paquete_salud))
                    
                    # Limpiamos para el siguiente usuario
                    temp_alcohol = None
                    temp_temperatura = None

            elif msg == "EVENTO:PASO":
                event_queue.put(("paso", msg))

        except Exception as exc:
            log(f"Error en listener serial: {exc}")
            break


def console_listener(uid_queue: queue.Queue, stop_event: threading.Event) -> None:
    log("Hilo de consola activo. Puedes escribir UID manual o 'salir'.")

    while not stop_event.is_set():
        try:
            uid = input("\nUID manual (o 'salir'): ").strip()
            if not uid:
                continue

            if uid.lower() == "salir":
                uid_queue.put(("system", "salir"))
                stop_event.set()
                break

            uid_queue.put(("manual", normalizar_uid(uid)))

        except EOFError:
            uid_queue.put(("system", "salir"))
            stop_event.set()
            break
        except Exception as exc:
            log(f"Error en consola: {exc}")
            uid_queue.put(("system", "salir"))
            stop_event.set()
            break


def preguntar_si_usa_serial() -> bool:
    while True:
        opcion = input("¿Quieres usar RFID físico por serial también? (s/n): ").strip().lower()
        if opcion in ("s", "si", "sí"):
            return True
        if opcion in ("n", "no"):
            return False


def main() -> None:
    log("Iniciando sistema...")

    db = Database(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
    )

    try:
        punto = db.get_punto_acceso(Config.PUNTO_ACCESO)
        log(f"Punto de acceso cargado: {punto['nombre']} ({punto['tipo_punto']})")

        usar_serial = preguntar_si_usa_serial()
        serial_mgr: Optional[SerialManager] = None

        if usar_serial:
            try:
                serial_mgr = SerialManager(
                    port=Config.SERIAL_PORT,
                    baudrate=Config.SERIAL_BAUDRATE,
                    timeout=Config.SERIAL_TIMEOUT,
                )
                log(f"Serial conectado en {Config.SERIAL_PORT}")
            except Exception as exc:
                log("Se continuará solo con captura manual.")
                serial_mgr = None

        uid_queue: queue.Queue[UidEvent] = queue.Queue()
        event_queue: queue.Queue[DeviceEvent] = queue.Queue()
        stop_event = threading.Event()

        t_console = threading.Thread(target=console_listener, args=(uid_queue, stop_event), daemon=True)
        t_console.start()

        if serial_mgr is not None:
            t_serial = threading.Thread(target=serial_listener, args=(serial_mgr, uid_queue, event_queue, stop_event), daemon=True)
            t_serial.start()

        while not stop_event.is_set():
            try:
                source, uid = uid_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if source == "system" and uid == "salir":
                stop_event.set()
                break

            try:
                procesar_uid(db, serial_mgr, punto, event_queue, uid, source)
            except Exception as exc:
                db.rollback()
                log(f"Error procesando UID [{uid}]: {exc}")
                if serial_mgr is not None:
                    try:
                        serial_mgr.send_command("CMD:DENEGAR")
                    except Exception:
                        pass

    except KeyboardInterrupt:
        log("Cierre por teclado")
    finally:
        try:
            if 'serial_mgr' in locals() and serial_mgr is not None:
                serial_mgr.close()
            db.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()