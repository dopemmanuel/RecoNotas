# ------------------------- BASE DE DATOS -------------------------
""" 
Aplica una conexion segura con al Base de dtos
"""
import sqlite3
import json
import logging
from threading import Lock

class SecureDB:
    """Implementa una conexión segura y gestionada a la base de datos SQLite."""
    _instance = None
    _lock = Lock()

    def __init__(self):
        self.conn = None
        self._initialize_db()

    @classmethod
    def get_instance(cls):
        """Obtiene la única instancia de la clase SecureDB (patrón Singleton)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _initialize_db(self):
        try:
            self.conn = sqlite3.connect("secure_reconotas.db", check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
        except sqlite3.Error as e:
            logging.error("Error al inicializar la base de datos: %s", str(e))
            raise

    def _create_tables(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lenguaje TEXT DEFAULT 'es',
                consentimiento_gdpr BOOLEAN DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                tipo_evento TEXT NOT NULL,
                detalles TEXT NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )""",
            """CREATE TABLE IF NOT EXISTS notas (
                id INTEGER PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                contenido_cifrado BLOB NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_modificacion TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )""",
            """CREATE TABLE IF NOT EXISTS recordatorios (
                id INTEGER PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                texto TEXT NOT NULL,
                hora_recordatorio TEXT NOT NULL,
                recurrente BOOLEAN DEFAULT 0,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completado BOOLEAN DEFAULT 0,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )""",
            """CREATE TABLE IF NOT EXISTS auth_2fa (
                usuario_id INTEGER PRIMARY KEY,
                secret TEXT NOT NULL,
                activado BOOLEAN DEFAULT 0,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )"""
        ]

        try:
            cursor = self.conn.cursor()
            for table in tables:
                cursor.execute(table)
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error("Error al crear tablas: %s", str(e))
            raise

    def registrar_auditoria(self, usuario_id: int, tipo_evento: str, detalles: dict):
        """Registra un evento de auditoría en la base de datos de forma segura."""
        try:
            self.conn.execute(
                """INSERT INTO auditoria 
                (usuario_id, tipo_evento, detalles) 
                VALUES (?, ?, ?)""",
                (usuario_id, tipo_evento, json.dumps(detalles))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error("Error en auditoría: %s", str(e))
            raise
