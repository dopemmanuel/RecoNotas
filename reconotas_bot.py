# -*- coding: utf-8 -*-
"""
RECONOTAS v2.1 - Bot de Telegram seguro y optimizado
"""

# ------------------------- IMPORTS -------------------------
import os
import sys
import io
import json
import logging
import sqlite3
from threading import Lock
from dotenv import load_dotenv
import telebot
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# ------------------------- CONFIGURACIÓN -------------------------
class Config:
    def __init__(self):
        # Configuración de encoding
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
        load_dotenv()
        
        # Verificación detallada de variables de entorno
        self.API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.API_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN no está configurado en el archivo .env")
            
        salt = os.getenv("ENCRYPTION_SALT")
        if not salt:
            raise ValueError("❌ ENCRYPTION_SALT no está configurado en el archivo .env")
        self.SALT = salt.encode()
        
        self.CLAVE_MAESTRA = os.getenv("ENCRYPTION_MASTER_PASSWORD")
        if not self.CLAVE_MAESTRA:
            raise ValueError("❌ ENCRYPTION_MASTER_PASSWORD no está configurado en el archivo .env")

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("auditoria.log", encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger("SecureBot")

# ------------------------- CIFRADO -------------------------
class CifradoManager:
    def __init__(self, salt: bytes, master_password: str):
        self.cipher = self._configurar_cifrado(salt, master_password)
    
    def _configurar_cifrado(self, salt: bytes, password: str) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return Fernet(key)
    
    def cifrar(self, texto: str) -> bytes:
        return self.cipher.encrypt(texto.encode('utf-8'))
    
    def descifrar(self, datos: bytes) -> str:
        try:
            return self.cipher.decrypt(datos).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Error de descifrado: {str(e)}") from e

# ------------------------- BASE DE DATOS -------------------------
class SecureDB:
    _instance = None
    _lock = Lock()

    def __init__(self):
        self.conn = None
        self._initialize_db()

    @classmethod
    def get_instance(cls):
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
            logging.error(f"Error al inicializar la base de datos: {str(e)}")
            raise

    def _create_tables(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            )"""
        ]
        
        try:
            cursor = self.conn.cursor()
            for table in tables:
                cursor.execute(table)
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error al crear tablas: {str(e)}")
            raise

    def registrar_auditoria(self, usuario_id: int, tipo_evento: str, detalles: dict):
        try:
            self.conn.execute(
                """INSERT INTO auditoria 
                (usuario_id, tipo_evento, detalles) 
                VALUES (?, ?, ?)""",
                (usuario_id, tipo_evento, json.dumps(detalles))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error en auditoría: {str(e)}")
            raise

# ------------------------- BOT PRINCIPAL -------------------------
class RecoNotasBot:
    def __init__(self, config_instance: Config):
        self.config = config_instance
        self.bot = telebot.TeleBot(config_instance.API_TOKEN)
        self.db = SecureDB.get_instance()
        self.cifrado = CifradoManager(config_instance.SALT, config_instance.CLAVE_MAESTRA)
        self._setup_handlers()

    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            try:
                user_id = message.from_user.id
                self.db.registrar_auditoria(
                    user_id, 
                    "INICIO_SESION", 
                    {"comando": message.text}
                )
                
                welcome_msg = (
                    "🔐 *Bienvenido a RecoNotas Seguro*\n\n"
                    "📝 **Funciones disponibles:**\n"
                    "/addnote - Añadir nota cifrada\n"
                    "/listnotes - Ver tus notas\n"
                    "/gdpr - Gestión de privacidad\n"
                )
                self.bot.reply_to(message, welcome_msg, parse_mode="Markdown")
                
            except telebot.apihelper.ApiTelegramException as e:
                self.config.logger.error(f"Error de API de Telegram: {str(e)}")
            except sqlite3.Error as e:
                self.config.logger.error(f"Error de base de datos: {str(e)}")
            except Exception as e:
                self.config.logger.error(f"Error inesperado: {str(e)}")
                raise

    def run(self):
        self.config.logger.info("Iniciando RecoNotas Secure v2.1")
        try:
            self.bot.polling(none_stop=True)
        except KeyboardInterrupt:
            self.config.logger.info("Bot detenido por el usuario")
            sys.exit(0)
        except telebot.apihelper.ApiTelegramException as e:
            self.config.logger.critical(f"Error crítico de API: {str(e)}")
            sys.exit(1)
        except Exception as e:
            self.config.logger.critical(f"Error crítico inesperado: {str(e)}")
            sys.exit(1)

# ------------------------- EJECUCIÓN -------------------------
if __name__ == "__main__":
    try:
        config_instance = Config()
        bot = RecoNotasBot(config_instance)
        bot.run()
    except ValueError as e:
        print(f"❌ Error de configuración: {str(e)}")
        print("ℹ️ Asegúrate de tener un archivo .env con todas las variables requeridas")
        sys.exit(1)
    except sqlite3.Error as e:
        print(f"❌ Error de base de datos: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")
        sys.exit(1)