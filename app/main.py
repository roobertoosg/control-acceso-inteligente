"""
Punto de Entrada Principal (Main Loop y Orquestador).

Este módulo actúa como el controlador principal de nuestro sistema embebido/servidor.
Su responsabilidad es:
1. Inicializar las conexiones (Base de Datos, Puerto Serial).
2. Levantar hilos (threads) paralelos para escuchar eventos físicos (RFID) y manuales (consola).
3. Encolar estos eventos y procesarlos secuencialmente para evitar condiciones de carrera en la BD.
4. Orquestar el flujo completo: Leer UID -> Decidir Acceso -> Activar Hardware -> Evaluar Anomalías -> Guardar.
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


UidEvent = Tuple[str, str]      # (source, uid)
DeviceEvent = Tuple[str, str]   # (event_type, raw_message)


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
) -> bool:
    """
    Espera activamente en la cola de eventos de hardware por un mensaje específico.
    Se usa principalmente para esperar la confirmación de "paso detectado" (sensor IR)
    después de abrir la puerta, con un tiempo límite definido.
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
            return True

    return False


def procesar_uid(
    db: Database,
    serial_mgr: Optional[SerialManager],
    punto: dict,
    event_queue: queue.Queue,
    uid: str,
    source: str,
) -> None:
    """
    Núcleo del procesamiento de un intento de acceso.
    
    Flujo:
    1. Consulta el estado del usuario.
    2. Pide permiso a `access_logic.py`.
    3. Si se permite, interactúa con el Arduino para abrir el servo y espera el paso.
    4. Evalúa posibles anomalías con `anomaly_logic.py` y registra todo en PostgreSQL.
    """
    uid = normalizar_uid(uid)

    if not uid:
        log("UID vacío, se ignora")
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
        log(
            f"Usuario encontrado: {nombre_completo} | "
            f"Matrícula: {usuario.get('matricula')} | "
            f"Estado actual: {usuario.get('estado_actual')}"
        )
    else:
        log("Usuario no encontrado")

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
            try:
                serial_mgr.send_command("CMD:DENEGAR")
            except Exception as exc:
                log(f"No se pudo enviar CMD:DENEGAR: {exc}")

        detalle = decision["detalle"]
        if analisis_denegacion["detalle_extra"]:
            detalle = f"{detalle} | {analisis_denegacion['detalle_extra']}"
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
            log(
                f"Denegación marcada como ANOMALIA | "
                f"motivo={analisis_denegacion['motivo_codigo']} | "
                f"score={analisis_denegacion['anomalia_score']}"
            )
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
            serial_mgr.send_command("CMD:PERMITIR")
        except Exception as exc:
            raise RuntimeError(f"No se pudo enviar CMD:PERMITIR: {exc}") from exc

        paso_ok = wait_for_queue_event(
            event_queue=event_queue,
            expected_type="paso",
            timeout_seconds=Config.PASO_TIMEOUT,
        )
    else:
        # Para demo / modo manual
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

        log("Evento incompleto registrado")
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

    motivo_final = db.get_motivo_by_codigo(analisis["motivo_codigo"])

    detalle_final = decision["detalle"]
    if analisis["detalle_extra"]:
        detalle_final = f"{detalle_final} | {analisis['detalle_extra']}"
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
        log(
            f"Evento registrado como ANOMALIA | "
            f"motivo={analisis['motivo_codigo']} | "
            f"score={analisis['anomalia_score']}"
        )
    else:
        log(f"Evento registrado. Nuevo estado del usuario: {decision['estado_nuevo']}")

    if serial_mgr is not None:
        try:
            serial_mgr.send_command("CMD:CERRAR")
        except Exception as exc:
            log(f"No se pudo enviar CMD:CERRAR: {exc}")


def serial_listener(
    serial_mgr: SerialManager,
    uid_queue: queue.Queue,
    event_queue: queue.Queue,
    stop_event: threading.Event,
) -> None:
    """
    Hilo de Escucha del Hardware (Arduino).
    
    Este hilo se dedica exclusivamente a leer el puerto serial sin bloquear el hilo principal.
    Cuando detecta una lectura RFID o un evento de paso, lo empaqueta y lo pone en las
    colas seguras (thread-safe) para que el hilo principal lo procese.
    """
    log("Hilo serial activo, esperando mensajes del Arduino...")

    while not stop_event.is_set():
        try:
            msg = serial_mgr.read_line()
            if not msg:
                continue

            msg = msg.strip()
            log(f"[SERIAL] {msg}")

            if msg.startswith("EVENTO:RFID:"):
                uid = normalizar_uid(msg.replace("EVENTO:RFID:", "", 1))
                if uid:
                    uid_queue.put(("rfid", uid))

            elif msg == "EVENTO:PASO":
                event_queue.put(("paso", msg))

        except Exception as exc:
            log(f"Error en listener serial: {exc}")
            break

    log("Hilo serial finalizado")


def console_listener(uid_queue: queue.Queue, stop_event: threading.Event) -> None:
    """
    Hilo de Escucha de Consola (Modo Debug/Manual).
    
    Permite a los desarrolladores o administradores inyectar UIDs manualmente a través
    de la terminal para simular lecturas RFID sin necesitar el hardware físico.
    """
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
            log(f"Error en listener de consola: {exc}")
            uid_queue.put(("system", "salir"))
            stop_event.set()
            break

    log("Hilo de consola finalizado")


def preguntar_si_usa_serial() -> bool:
    while True:
        opcion = input("¿Quieres usar RFID físico por serial también? (s/n): ").strip().lower()
        if opcion in ("s", "si", "sí"):
            return True
        if opcion in ("n", "no"):
            return False
        print("Respuesta no válida. Escribe 's' o 'n'.")


def main() -> None:
    """
    Punto de arranque de la aplicación.
    Configura el entorno, decide si usar hardware físico o modo de prueba,
    levanta los hilos de escucha y comienza el loop infinito de procesamiento de eventos.
    """
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
                log(
                    f"Serial conectado en {Config.SERIAL_PORT} "
                    f"a {Config.SERIAL_BAUDRATE} baudios"
                )
            except Exception as exc:
                log(f"No se pudo abrir el puerto serial: {exc}")
                log("Se continuará solo con captura manual.")
                serial_mgr = None
        else:
            log("Modo manual seleccionado. No se usará RFID físico por serial.")

        uid_queue: queue.Queue[UidEvent] = queue.Queue()
        event_queue: queue.Queue[DeviceEvent] = queue.Queue()
        stop_event = threading.Event()

        t_console = threading.Thread(
            target=console_listener,
            args=(uid_queue, stop_event),
            daemon=True,
        )
        t_console.start()

        if serial_mgr is not None:
            t_serial = threading.Thread(
                target=serial_listener,
                args=(serial_mgr, uid_queue, event_queue, stop_event),
                daemon=True,
            )
            t_serial.start()

        log("Sistema listo. Esperando UID manual o RFID físico...")

        while not stop_event.is_set():
            try:
                source, uid = uid_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if source == "system" and uid == "salir":
                log("Solicitud de salida recibida")
                stop_event.set()
                break

            try:
                procesar_uid(
                    db=db,
                    serial_mgr=serial_mgr,
                    punto=punto,
                    event_queue=event_queue,
                    uid=uid,
                    source=source,
                )
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
        except Exception:
            pass

        try:
            db.close()
        except Exception:
            pass

        log("Sistema finalizado")


if __name__ == "__main__":
    main()