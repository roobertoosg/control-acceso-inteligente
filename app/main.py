from config import Config
from db import Database
from serial_manager import SerialManager
from access_logic import decidir_evento
from utils import log


def main() -> None:
    log("Iniciando sistema...")

    db = Database(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
    )

    serial_mgr = SerialManager(
        port=Config.SERIAL_PORT,
        baudrate=Config.SERIAL_BAUDRATE,
        timeout=Config.SERIAL_TIMEOUT,
    )

    punto = db.get_punto_acceso(Config.PUNTO_ACCESO)
    log(f"Punto de acceso cargado: {punto['nombre']}")

    try:
        while True:
            uid = input("\nEscanea/escribe UID (o 'salir'): ").strip()

            if not uid:
                continue

            if uid.lower() == "salir":
                break

            usuario = db.get_usuario_by_uid(uid)
            decision = decidir_evento(usuario)
            motivo = db.get_motivo_by_codigo(decision["motivo_codigo"])

            log(f"UID recibido: {uid}")

            if usuario:
                nombre_completo = " ".join(
                    x for x in [
                        usuario["nombre"],
                        usuario["apellido_paterno"],
                        usuario["apellido_materno"],
                    ] if x
                )
                log(f"Usuario encontrado: {nombre_completo} | Estado actual: {usuario['estado_actual']}")
            else:
                log("Usuario no encontrado")

            if not decision["permitido"]:
                log("Acceso denegado")
                serial_mgr.send_command("CMD:DENEGAR")

                db.insert_evento(
                    id_usuario=usuario["id_usuario"] if usuario else None,
                    uid_rfid_leido=uid,
                    id_punto=punto["id_punto"],
                    modo_evento=decision["modo_evento"],
                    resultado=decision["resultado"],
                    id_motivo=motivo["id_motivo"],
                    estado_anterior=decision["estado_anterior"],
                    estado_nuevo=decision["estado_nuevo"],
                    paso_detectado=False,
                    servo_activado=False,
                    anomalia_score=20,
                    detalle=decision["detalle"],
                )
                db.commit()
                log("Evento denegado registrado en BD")
                continue

            # Permitido
            log(f"{decision['detalle']} -> enviando CMD:PERMITIR")
            serial_mgr.clear_input()
            serial_mgr.send_command("CMD:PERMITIR")

            paso_ok = serial_mgr.wait_for_message("EVENTO:PASO", Config.PASO_TIMEOUT)

            if paso_ok:
                log("Paso detectado, registrando evento")
                db.insert_evento(
                    id_usuario=usuario["id_usuario"],
                    uid_rfid_leido=uid,
                    id_punto=punto["id_punto"],
                    modo_evento=decision["modo_evento"],
                    resultado=decision["resultado"],
                    id_motivo=motivo["id_motivo"],
                    estado_anterior=decision["estado_anterior"],
                    estado_nuevo=decision["estado_nuevo"],
                    paso_detectado=True,
                    servo_activado=True,
                    anomalia_score=0,
                    detalle=decision["detalle"],
                )
                db.update_estado_usuario(usuario["id_usuario"], decision["estado_nuevo"])
                db.commit()
                log(f"Evento registrado. Nuevo estado: {decision['estado_nuevo']}")
                serial_mgr.send_command("CMD:CERRAR")
            else:
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
                    servo_activado=True,
                    anomalia_score=10,
                    detalle="Se autorizó el acceso, pero no se detectó paso",
                )
                db.commit()
                serial_mgr.send_command("CMD:CERRAR")
                log("Evento incompleto registrado")

    except KeyboardInterrupt:
        log("Cierre por teclado")
    except Exception as exc:
        db.rollback()
        log(f"Error: {exc}")
        raise
    finally:
        serial_mgr.close()
        db.close()
        log("Sistema finalizado")


if __name__ == "__main__":
    main()