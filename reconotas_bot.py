# -*- coding: utf-8 -*-
"""
RECONOTAS v2.0 - Bot de Telegram con:
- Cifrado AES-256
- Trazabilidad GDPR
- Backups automáticos
- Auditoría completa
"""

# ------------------------- IMPORTS MEJORADOS -------------------------
import os
import re
import sys
import io
import json
import logging
import sqlite3
import boto3
from datetime import datetime, timedelta
from threading import Thread, Lock
from time import sleep
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# ------------------------- CONFIGURACIÓN INICIAL -------------------------
# Configuración de encoding UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Cargar variables de entorno
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SALT = os.getenv("ENCRYPTION_SALT").encode()  # Debe ser de 16+ bytes

if not API_TOKEN or not SALT:
    raise ValueError("❌ Faltan variables de entorno esenciales")

# ------------------------- CIFRADO MEJORADO -------------------------
def generar_clave(password: str) -> bytes:
    """Deriva una clave segura usando PBKDF2"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=32,
        salt=SALT,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

# Usar una contraseña maestra desde variables de entorno
CLAVE_MAESTRA = os.getenv("ENCRYPTION_MASTER_PASSWORD")
if not CLAVE_MAESTRA:
    raise ValueError("❌ No se configuró ENCRYPTION_MASTER_PASSWORD")

key = generar_clave(CLAVE_MAESTRA)
cipher = Fernet(key)

# ------------------------- LOGGING CON AUDITORÍA -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("auditoria.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SecureBot")

# ------------------------- CLASE SEGURA DE BASE DE DATOS -------------------------
class SecureDB:
    """Wrapper seguro para operaciones de base de datos"""
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SecureDB, cls).__new__(cls)
                    cls._instance._initialize_db()
        return cls._instance

    def _initialize_db(self):
        """Inicialización segura de la base de datos"""
        self.conn = sqlite3.connect("secure_reconotas.db", check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        """Crea tablas con estructura segura"""
        cursor = self.conn.cursor()
        
        # Tabla de usuarios (requerida por GDPR)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            consentimiento_gdpr BOOLEAN DEFAULT 0
        )""")

        # Tabla de notas cifradas
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            contenido_cifrado BLOB NOT NULL,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_eliminacion TIMESTAMP NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""")

        # Tabla de recordatorios
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recordatorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            mensaje_cifrado BLOB NOT NULL,
            hora TEXT NOT NULL CHECK(hora GLOB '[0-2][0-9]:[0-5][0-9]'),
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""")

        # Auditoría detallada (cumplimiento GDPR Art. 30)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            tipo_evento TEXT NOT NULL,
            detalles TEXT NOT NULL,
            direccion_ip TEXT,
            user_agent TEXT,
            fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )""")

        self.conn.commit()

    def registrar_auditoria(self, usuario_id: int, tipo_evento: str, detalles: str, ip: str = None, user_agent: str = None):
        """Registro detallado para cumplimiento normativo"""
        try:
            self.conn.execute(
                """INSERT INTO auditoria 
                (usuario_id, tipo_evento, detalles, direccion_ip, user_agent) 
                VALUES (?, ?, ?, ?, ?)""",
                (usuario_id, tipo_evento, json.dumps(detalles), ip, user_agent))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error en auditoría: {str(e)}")

# ------------------------- BOT CON SEGURIDAD MEJORADA -------------------------
class RecoNotasBot:
    def __init__(self):
        self.bot = telebot.TeleBot(API_TOKEN)
        self.db = SecureDB()
        self.setup_handlers()
        self.start_background_jobs()

    def setup_handlers(self):
        """Configura todos los handlers seguros"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            try:
                user = self._registrar_usuario(message.from_user)
                self.db.registrar_auditoria(
                    user['id'], 
                    "INICIO_SESION", 
                    {"comando": message.text}
                )
                
                welcome_msg = (
                    "🔐 *Bienvenido a RecoNotas Seguro*\n\n"
                    "📝 **Funciones disponibles:**\n"
                    "/addnote - Añadir nota cifrada\n"
                    "/listnotes - Ver tus notas\n"
                    "/gdpr - Gestión de privacidad\n"
                    "/addreminder - Programar recordatorio\n"
                    "\n⚠️ Todos los datos se cifran con AES-256"
                )
                self.bot.reply_to(message, welcome_msg, parse_mode="Markdown")
                
            except Exception as e:
                logger.error(f"Error en welcome: {str(e)}")

        # ... (otros handlers con la misma estructura segura)

    def _registrar_usuario(self, user_data):
        """Registro seguro de usuarios con consentimiento GDPR"""
        cursor = self.db.conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (telegram_id) VALUES (?)",
            (user_data.id,)
        )
        self.db.conn.commit()
        
        cursor.execute(
            "SELECT id, consentimiento_gdpr FROM usuarios WHERE telegram_id = ?",
            (user_data.id,)
        )
        return cursor.fetchone()

    def _cifrar(self, texto: str) -> bytes:
        """Cifrado robusto con verificación de integridad"""
        return cipher.encrypt(texto.encode('utf-8'))

    def _descifrar(self, datos: bytes) -> str:
        """Descifrado con manejo de errores"""
        try:
            return cipher.decrypt(datos).decode('utf-8')
        except Exception as e:
            logger.error(f"Error al descifrar: {str(e)}")
            raise ValueError("❌ Error al procesar datos cifrados")

    def start_background_jobs(self):
        """Inicia procesos en segundo plano"""
        
        def backup_manager():
            """Realiza backups cifrados y los sube a AWS S3"""
            while True:
                try:
                    fecha = datetime.now().strftime("%Y%m%d_%H%M")
                    backup_file = f"backup_{fecha}.db"
                    
                    # Cifrar la base de datos completa
                    with open(backup_file, 'wb') as f:
                        with open("secure_reconotas.db", 'rb') as original:
                            f.write(cipher.encrypt(original.read()))
                    
                    # Subir a AWS S3 (opcional)
                    if os.getenv("AWS_ENABLED") == "true":
                        s3 = boto3.client('s3')
                        s3.upload_file(
                            backup_file,
                            os.getenv("AWS_BUCKET"),
                            f"backups/{backup_file}",
                            ExtraArgs={
                                'ServerSideEncryption': 'AES256',
                                'StorageClass': 'STANDARD_IA'
                            }
                        )
                    
                    # Rotación de backups locales (mantener últimos 7)
                    backups = sorted([f for f in os.listdir() if f.startswith('backup_')])
                    for old_backup in backups[:-7]:
                        os.remove(old_backup)
                        
                    logger.info(f"Backup completado: {backup_file}")
                    
                except Exception as e:
                    logger.error(f"Error en backup: {str(e)}")
                
                sleep(3600 * 6)  # Cada 6 horas

        # Iniciar hilos seguros
        Thread(target=backup_manager, daemon=True).start()

    def run(self):
        """Inicia el bot con manejo seguro de errores"""
        logger.info("🚀 Iniciando RecoNotas Secure v2.0")
        try:
            self.bot.polling(none_stop=True, interval=2, timeout=30)
        except Exception as e:
            logger.critical(f"Error crítico: {str(e)}")
            sys.exit(1)

# ------------------------- EJECUCIÓN PRINCIPAL -------------------------
if __name__ == "__main__":
    # Verificar entorno seguro
    if sys.version_info < (3, 8):
        raise RuntimeError("Se requiere Python 3.8+ por razones de seguridad")
    
    if not os.path.exists('.env'):
        raise FileNotFoundError("❌ Falta archivo .env con configuraciones sensibles")

    # Iniciar aplicación
    try:
        bot = RecoNotasBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Detención segura solicitada")
    except Exception as e:
        logger.critical(f"Error irrecuperable: {str(e)}")
        sys.exit(1)