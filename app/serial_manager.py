"""
Administrador de Comunicaciones Seriales.

Este módulo encapsula la librería `pyserial`. Su único propósito es servir
de puente entre nuestro backend en Python y el microcontrolador (Arduino/ESP)
que controla físicamente la lectura de las tarjetas RFID, la apertura del servo,
y la lectura del sensor infrarrojo de paso.
"""
import time
from typing import Optional

import serial


class SerialManager:
    def __init__(self, port: str, baudrate: int, timeout: float = 1.0):
        self.ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        time.sleep(2)

    def send_command(self, cmd: str) -> None:
        line = cmd.strip() + "\n"
        self.ser.write(line.encode("utf-8"))
        self.ser.flush()

    def read_line(self) -> Optional[str]:
        raw = self.ser.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="ignore").strip()

    def clear_input(self) -> None:
        self.ser.reset_input_buffer()

    def wait_for_message(self, expected: str, timeout_seconds: int) -> bool:
        start = time.time()
        while time.time() - start < timeout_seconds:
            msg = self.read_line()
            if not msg:
                continue
            print(f"[SERIAL] {msg}")
            if msg == expected:
                return True
        return False

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()