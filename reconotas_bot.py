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
from threading import Lock, Timer
from datetime import datetime, timedelta
import base64
from dotenv import load_dotenv
import telebot
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# ------------------------- CONFIGURACIÓN -------------------------
class Config:
    """
    Contiene la conigurcion interna para el bot
    """

    def __init__(self):
        # Configuración de encoding
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

        load_dotenv()

        # Verificación detallada de variables de entorno
        self.api_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.api_token:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN no está configurado en el archivo .env")

        salt = os.getenv("ENCRYPTION_SALT")
        if not salt:
            raise ValueError("❌ ENCRYPTION_SALT no está configurado en el archivo .env")
        self.salt = salt.encode()

        self.clave_maestra = os.getenv("ENCRYPTION_MASTER_PASSWORD")
        if not self.clave_maestra:
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
    """Crea un cifrado para encriptar info sencible 
    """
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
        """Cifra un texto plano usando la clave maestra configurada."""
        return self.cipher.encrypt(texto.encode('utf-8'))

    def descifrar(self, datos: bytes) -> str:
        """Descifra datos previamente cifrados usando la clave maestra configurada."""
        try:
            return self.cipher.decrypt(datos).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Error de descifrado: {str(e)}") from e

# ------------------------- BASE DE DATOS -------------------------
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
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completado BOOLEAN DEFAULT 0,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )"""
        ]

        try:
            cursor = self.conn.cursor()
            for table in tables:
                cursor.execute(table)
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error("Error al crear tablas: %s" , str(e))
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

# ------------------------- BOT PRINCIPAL -------------------------
class RecoNotasBot:
    """
    La clase principal para el bot
    """
    def __init__(self, config: Config):
        self.config = config
        self.bot = telebot.TeleBot(config.api_token)
        self.db = SecureDB.get_instance()
        self.cifrado = CifradoManager(config.salt, config.clave_maestra)
        self.active_reminders = {}
        self._setup_handlers()
        self._load_pending_reminders()

    def _load_pending_reminders(self):
        """Carga recordatorios pendientes al iniciar el bot"""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute(
                """SELECT r.id, u.telegram_id, r.texto, r.hora_recordatorio 
                FROM recordatorios r
                JOIN usuarios u ON r.usuario_id = u.id
                WHERE r.completado = 0"""
            )
            reminders = cursor.fetchall()
            
            for reminder_id, user_id, text, reminder_time in reminders:
                self._schedule_reminder(user_id, reminder_time, text, reminder_id)
                
        except Exception as e:
            self.config.logger.error(f"Error cargando recordatorios: {str(e)}")

    def _schedule_reminder(self, user_id, reminder_time, text, reminder_id=None):
        """Programa un recordatorio para enviarse a la hora especificada"""
        try:
            now = datetime.now()
            target_time = datetime.strptime(reminder_time, "%H:%M").time()
            target_datetime = datetime.combine(now.date(), target_time)
            
            if target_datetime < now:
                target_datetime += timedelta(days=1)
                
            delay = (target_datetime - now).total_seconds()
            
            t = Timer(delay, self._send_reminder, args=(user_id, text, reminder_id))
            t.start()
            
            self.active_reminders[(user_id, text)] = t
            
        except Exception as e:
            self.config.logger.error(f"Error programando recordatorio: {str(e)}")

    def _send_reminder(self, user_id, text, reminder_id=None):
        """Envía el recordatorio al usuario y lo marca como completado"""
        try:
            self.bot.send_message(user_id, f"🔔 Recordatorio: {text}")
            
            if reminder_id:
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "UPDATE recordatorios SET completado = 1 WHERE id = ?",
                    (reminder_id,)
                )
                self.db.conn.commit()
                
        except Exception as e:
            self.config.logger.error(f"Error enviando recordatorio: {str(e)}")
        finally:
            if (user_id, text) in self.active_reminders:
                del self.active_reminders[(user_id, text)]

    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            try:
                user = message.from_user
                user_id = user.id
            
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO usuarios (telegram_id) VALUES (?)",
                    (user_id,)
                )
                self.db.conn.commit()
                
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]
                
                self.db.registrar_auditoria(
                    db_user_id,
                    "INICIO_SESION",
                    {
                        "comando": message.text,
                        "username": user.username,
                        "first_name": user.first_name
                    }
                )

                welcome_msg = (
                    "🔐 *Bienvenido a RecoNotas Seguro*\n\n"
                    "📝 **Funciones disponibles:**\n"
                    "/addnote - Añadir nota cifrada\n"
                    "/listnotes - Ver tus notas\n"
                    "/deletenote - Eliminar una nota\n"
                    "/addreminder - Añadir recordatorio\n"
                    "/listreminders - Ver recordatorios\n"
                    "/gdpr - Gestión de privacidad\n"
                )
                self.bot.reply_to(message, welcome_msg, parse_mode="Markdown")

            except Exception as e:
                self.config.logger.error(f"Error en send_welcome: {str(e)}")
                self.bot.reply_to(message, "❌ Ocurrió un error al procesar tu solicitud")

        @self.bot.message_handler(commands=['addnote'])
        def add_note(message):
            try:
                msg = self.bot.reply_to(message, "📝 Envíame el texto de la nota que quieres guardar:")
                self.bot.register_next_step_handler(msg, self._process_note_step)
            except Exception as e:
                self.config.logger.error(f"Error en add_note: {str(e)}")
                self.bot.reply_to(message, "❌ Ocurrió un error al procesar tu nota")

        @self.bot.message_handler(commands=['listnotes'])
        def list_notes(message):
            try:
                user_id = message.from_user.id
                
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]
                
                cursor.execute(
                    "SELECT id, contenido_cifrado, fecha_creacion FROM notas WHERE usuario_id = ?",
                    (db_user_id,)
                )
                notes = cursor.fetchall()
                
                if not notes:
                    self.bot.reply_to(message, "📭 No tienes ninguna nota guardada")
                    return
                    
                response = "📖 *Tus notas:*\n\n"
                for note_id, encrypted_note, fecha in notes:
                    decrypted_note = self.cifrado.descifrar(encrypted_note)
                    short_note = (decrypted_note[:50] + '...') if len(decrypted_note) > 50 else decrypted_note
                    response += f"🆔 {note_id}\n📅 {fecha}\n📝 {short_note}\n\n"
                    
                self.bot.reply_to(message, response, parse_mode="Markdown")
                
            except Exception as e:
                self.config.logger.error(f"Error en list_notes: {str(e)}")
                self.bot.reply_to(message, "❌ Error al listar las notas")

        @self.bot.message_handler(commands=['addreminder'])
        def add_reminder(message):
            try:
                msg = self.bot.reply_to(message, "⏰ ¿Qué quieres que te recuerde? Envía el texto del recordatorio:")
                self.bot.register_next_step_handler(msg, self._process_reminder_text_step)
            except Exception as e:
                self.config.logger.error(f"Error en add_reminder: {str(e)}")
                self.bot.reply_to(message, "❌ Ocurrió un error al crear el recordatorio")

        @self.bot.message_handler(commands=['listreminders'])
        def list_reminders(message):
            try:
                user_id = message.from_user.id
                
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]
                
                cursor.execute(
                    """SELECT id, texto, hora_recordatorio 
                    FROM recordatorios 
                    WHERE usuario_id = ? AND completado = 0
                    ORDER BY hora_recordatorio""",
                    (db_user_id,)
                )
                reminders = cursor.fetchall()
                
                if not reminders:
                    self.bot.reply_to(message, "⏳ No tienes recordatorios pendientes")
                    return
                    
                response = "⏰ *Tus recordatorios pendientes:*\n\n"
                for reminder_id, text, reminder_time in reminders:
                    response += f"🆔 {reminder_id}\n⏰ {reminder_time}\n📝 {text}\n\n"
                    
                self.bot.reply_to(message, response, parse_mode="Markdown")
                
            except Exception as e:
                self.config.logger.error(f"Error en list_reminders: {str(e)}")
                self.bot.reply_to(message, "❌ Error al listar los recordatorios")

    def _process_note_step(self, message):
        """Procesa el texto de la nota recibido"""
        try:
            user_id = message.from_user.id
            note_text = message.text
            
            if not note_text or len(note_text.strip()) == 0:
                self.bot.reply_to(message, "❌ El texto de la nota no puede estar vacío")
                return
                
            if len(note_text) > 2000:
                self.bot.reply_to(message, "❌ La nota es demasiado larga (máximo 2000 caracteres)")
                return
            
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
            db_user_id = cursor.fetchone()[0]
            
            encrypted_note = self.cifrado.cifrar(note_text)
            cursor.execute(
                "INSERT INTO notas (usuario_id, contenido_cifrado) VALUES (?, ?)",
                (db_user_id, encrypted_note)
            )
            self.db.conn.commit()
            
            self.bot.reply_to(message, "✅ Nota guardada correctamente")
            
            self.db.registrar_auditoria(
                db_user_id,
                "NOTA_CREADA",
                {"tamaño": len(note_text)}
            )
        except Exception as e:
            self.db.conn.rollback()
            self.config.logger.error(f"Error en _process_note_step: {str(e)}")
            self.bot.reply_to(message, "❌ Error al guardar la nota")

    def _process_reminder_text_step(self, message):
        """Procesa el texto del recordatorio y pide la hora"""
        try:
            if not hasattr(message, 'text') or not message.text:
                self.bot.reply_to(message, "❌ Debes proporcionar un texto para el recordatorio")
                return
                
            reminder_text = message.text
            
            msg = self.bot.reply_to(
                message, 
                "🕒 ¿A qué hora quieres que te lo recuerde? (Formato HH:MM, ej. 14:30)"
            )
            self.bot.register_next_step_handler(
                msg, 
                lambda m: self._process_reminder_time_step(m, reminder_text)
            )
        except Exception as e:
            self.config.logger.error(f"Error en _process_reminder_text_step: {str(e)}")
            self.bot.reply_to(message, "❌ Ocurrió un error al procesar tu recordatorio")

    def _process_reminder_time_step(self, message, reminder_text):
        """Procesa la hora del recordatorio y lo guarda"""
        try:
            reminder_time = message.text
            
            # Validar formato de hora
            try:
                datetime.strptime(reminder_time, "%H:%M")
            except ValueError:
                self.bot.reply_to(message, "❌ Formato de hora inválido. Usa HH:MM (ej. 14:30)")
                return
                
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (message.from_user.id,))
            db_user_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT INTO recordatorios (usuario_id, texto, hora_recordatorio) VALUES (?, ?, ?)",
                (db_user_id, reminder_text, reminder_time)
            )
            reminder_id = cursor.lastrowid
            self.db.conn.commit()
            
            self._schedule_reminder(message.from_user.id, reminder_time, reminder_text, reminder_id)
            
            self.bot.reply_to(
                message, 
                f"✅ Recordatorio programado para las {reminder_time}\n"
                f"📝 Texto: {reminder_text}"
            )
            
            self.db.registrar_auditoria(
                db_user_id,
                "RECORDATORIO_CREADO",
                {"hora": reminder_time, "tamaño_texto": len(reminder_text)}
            )
        except Exception as e:
            self.db.conn.rollback()
            self.config.logger.error(f"Error en _process_reminder_time_step: {str(e)}")
            self.bot.reply_to(message, "❌ Error al programar el recordatorio")

    def run(self):
        """Inicia el bot"""
        self.config.logger.info("Iniciando RecoNotas Secure v2.1")
        try:
            self.bot.polling(none_stop=True)
        except KeyboardInterrupt:
            self.config.logger.info("Bot detenido por el usuario")
            sys.exit(0)
        except Exception as e:
            self.config.logger.critical(f"Error crítico: {str(e)}")
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
    except Exception as e: 
        print(f"❌ Error inesperado: {str(e)}")
        sys.exit(1)
