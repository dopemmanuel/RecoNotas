# -*- coding: utf-8 -*-
"""
RECONOTAS v2.4 <- 2.3 RELOADED Bot de Telegram seguro y optimizado con autenticación 2FA y multiidioma
"""

# ------------------------- IMPORTS -------------------------
import os
import sys
import io
import json
import logging
import sqlite3
import gettext
from threading import Lock, Timer
from datetime import datetime, timedelta
import base64
from pathlib import Path
from dotenv import load_dotenv
import telebot
import pyotp
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# ------------------------- CONFIGURACIÓN -------------------------
class Config:
    """
    Contiene la configuración interna para el bot
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

        # Configuración de internacionalización
        self.locales_dir = Path(__file__).parent / 'locales'
        self.supported_langs = ['es', 'en', 'pt']
        self.default_lang = 'es'

        # Configuración 2FA
        self.totp_secret = os.getenv("TOTP_SECRET", pyotp.random_base32())

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
    """Crea un cifrado para encriptar info sensible"""
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
        self._load_translations()
        self._setup_handlers()
        self._load_pending_reminders()
        self._clear_console()

    def _clear_console(self):
        """Limpia la consola según el sistema operativo"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _load_translations(self):
        """Carga las traducciones para multiidioma"""
        self.translations = {}
        for lang in self.config.supported_langs:
            try:
                self.translations[lang] = gettext.translation(
                    'reconotas',
                    localedir=self.config.locales_dir,
                    languages=[lang],
                    fallback=True
                )
            except FileNotFoundError:
                self.translations[lang] = gettext.NullTranslations()

    def _get_user_translation(self, user_id):
        """Obtiene la traducción para el idioma del usuario"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT lenguaje FROM usuarios WHERE telegram_id = ?", (user_id,))
        lang = cursor.fetchone()
        lang = lang[0] if lang else self.config.default_lang
        return self.translations.get(lang, self.translations[self.config.default_lang]).gettext

    def _get_main_menu(self):
        """Devuelve el teclado principal del menú"""
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            '📝 Añadir Nota',
            '📖 Listar Notas',
            '🗑 Eliminar Nota',
            '⏰ Añadir Recordatorio',
            '🔄 Listar Recordatorios',
            '⚙️ Configuración'
        )
        return markup

    def _load_pending_reminders(self):
        """Carga recordatorios pendientes al iniciar el bot"""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute(
                """SELECT r.id, u.telegram_id, r.texto, r.hora_recordatorio, r.recurrente 
                FROM recordatorios r
                JOIN usuarios u ON r.usuario_id = u.id
                WHERE r.completado = 0"""
            )
            reminders = cursor.fetchall()
            
            for reminder_id, user_id, text, reminder_time, recurrente in reminders:
                self._schedule_reminder(user_id, reminder_time, text, reminder_id, recurrente)
                
        except Exception as e:
            self.config.logger.error(f"Error cargando recordatorios: {str(e)}")

    def _schedule_reminder(self, user_id, reminder_time, text, reminder_id=None, recurrente=False):
        """Programa un recordatorio para enviarse a la hora especificada"""
        try:
            now = datetime.now()
            target_time = datetime.strptime(reminder_time, "%H:%M").time()
            target_datetime = datetime.combine(now.date(), target_time)
            
            if target_datetime < now:
                target_datetime += timedelta(days=1)
                
            delay = (target_datetime - now).total_seconds()
            
            if recurrente:
                t = Timer(delay, self._setup_recurrent_reminder, args=(user_id, reminder_time, text, reminder_id))
            else:
                t = Timer(delay, self._send_reminder, args=(user_id, text, reminder_id))
            
            t.start()
            self.active_reminders[(user_id, text)] = t
            
        except Exception as e:
            self.config.logger.error(f"Error programando recordatorio: {str(e)}")

    def _setup_recurrent_reminder(self, user_id, reminder_time, text, reminder_id=None):
        """Configura un recordatorio recurrente diario"""
        try:
            # Enviar el recordatorio actual
            self._send_reminder(user_id, text, reminder_id)
            
            # Programar para el siguiente día
            next_day = datetime.now() + timedelta(days=1)
            delay = (next_day - datetime.now()).total_seconds()
            
            t = Timer(delay, self._setup_recurrent_reminder, args=(user_id, reminder_time, text, reminder_id))
            t.start()
            self.active_reminders[(user_id, text)] = t
            
        except Exception as e:
            self.config.logger.error(f"Error en recordatorio recurrente: {str(e)}")

    def _send_reminder(self, user_id, text, reminder_id=None):
        """Envía el recordatorio al usuario y lo marca como completado"""
        try:
            _ = self._get_user_translation(user_id)
            self.bot.send_message(user_id, _("🔔 Recordatorio: {text}").format(text=text))
            
            if reminder_id:
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "UPDATE recordatorios SET completado = 1 WHERE id = ? AND recurrente = 0",
                    (reminder_id,)
                )
                self.db.conn.commit()
                
        except Exception as e:
            self.config.logger.error(f"Error enviando recordatorio: {str(e)}")
        finally:
            if (user_id, text) in self.active_reminders:
                del self.active_reminders[(user_id, text)]

#---------------------

    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help', 'menu'])
        def send_welcome(message):
            try:
                user = message.from_user
                user_id = user.id
            
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO usuarios (telegram_id, lenguaje) VALUES (?, ?)",
                    (user_id, self.config.default_lang)
                )
                self.db.conn.commit()
                
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]
                
                # Verificar 2FA si está activado
                cursor.execute("SELECT secret FROM auth_2fa WHERE usuario_id = ? AND activado = 1", (db_user_id,))
                if cursor.fetchone():
                    msg = self.bot.reply_to(message, "🔐 Ingresa tu código 2FA:")
                    self.bot.register_next_step_handler(msg, lambda m: self._verify_2fa(m, db_user_id))
                    return
                
                self._show_main_menu(message, db_user_id)
                
            except Exception as e:
                self.config.logger.error(f"Error en send_welcome: {str(e)}")
                self.bot.reply_to(message, "❌ Ocurrió un error al procesar tu solicitud")

    def _verify_2fa(self, message, db_user_id):
        """Verifica el código 2FA del usuario"""
        try:
            user_code = message.text
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT secret FROM auth_2fa WHERE usuario_id = ?", (db_user_id,))
            secret = cursor.fetchone()[0]
            
            if pyotp.TOTP(secret).verify(user_code):
                self._show_main_menu(message, db_user_id)
            else:
                self.bot.reply_to(message, "❌ Código inválido. Intenta nuevamente o usa /start")
        except Exception as e:
            self.config.logger.error(f"Error en verify_2fa: {str(e)}")
            self.bot.reply_to(message, "❌ Error en autenticación")

    def _show_main_menu(self, message, db_user_id):
        """Muestra el menú principal al usuario"""
        _ = self._get_user_translation(message.from_user.id)
        welcome_msg = _(
            "🔐 *Bienvenido a RecoNotas Seguro*\n\n"
            "📝 **Selecciona una opción del menú:**\n"
            "O usa los comandos tradicionales si lo prefieres"
        )
        self.bot.reply_to(
            message,
            welcome_msg,
            parse_mode="Markdown",
            reply_markup=self._get_main_menu()
        )

        # Registrar auditoría
        self.db.registrar_auditoria(
            db_user_id,
            "INICIO_SESION",
            {
                "comando": message.text,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name
            }
        )

        # Manejador para los botones del menú
        @self.bot.message_handler(func=lambda message: True)
        def handle_menu_buttons(message):
            try:
                text = message.text.lower()
                _ = self._get_user_translation(message.from_user.id)

                if 'añadir nota' in text or 'addnote' in text:
                    add_note(message)
                elif 'listar notas' in text or 'listnotes' in text:
                    list_notes(message)
                elif 'eliminar nota' in text or 'deletenote' in text:
                    delete_note(message)
                elif 'añadir recordatorio' in text or 'addreminder' in text:
                    add_reminder(message)
                elif 'listar recordatorios' in text or 'listreminders' in text:
                    list_reminders(message)
                elif 'configuración' in text or 'settings' in text:
                    show_settings(message)
                else:
                    self.bot.reply_to(
                        message, 
                        _("No reconozco ese comando. Usa el menú o escribe /help"),
                        reply_markup=self._get_main_menu()
                    )
                    
            except Exception as e:
                self.config.logger.error(f"Error en handle_menu_buttons: {str(e)}")
                self.bot.reply_to(
                    message, 
                    "❌ Ocurrió un error al procesar tu solicitud",
                    reply_markup=self._get_main_menu()
                )

        @self.bot.message_handler(commands=['tutorial', 'help'])
        def show_tutorial(message):
            try:
                _ = self._get_user_translation(message.from_user.id)
                tutorial_markdown = _(
                    "📚 *Tutorial de RecoNotas*\n\n"
                    "1. *Notas*:\n"
                    "   - /newnote [texto] - Crea una nota\n"
                    "   - /mynotes - Lista tus notas\n\n"
                    "2. *Recordatorios*:\n"
                    "   - /newreminder [texto] [HH:MM] --recurrente\n"
                    "   - /myreminders - Lista recordatorios\n\n"
                    "3. *Seguridad*:\n"
                    "   - /setup2fa - Configura autenticación\n"
                    "   - /settings - Cambia preferencias\n\n"
                    "ℹ️ Usa el menú de botones para acceso rápido!"
                )
                
                self.bot.reply_to(
                    message,
                    tutorial_markdown,
                    parse_mode="Markdown",
                    reply_markup=self._get_main_menu()
                )
            except Exception as e:
                self.config.logger.error(f"Error en show_tutorial: {str(e)}")
                self.bot.reply_to(message, "❌ Error al mostrar el tutorial")

        @self.bot.message_handler(commands=['setup2fa'])
        def setup_2fa(message):
            try:
                user_id = message.from_user.id
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]

                # Generar nuevo secreto
                secret = pyotp.random_base32()
                totp = pyotp.TOTP(secret)
                provisioning_uri = totp.provisioning_uri(name=str(user_id), issuer_name="RecoNotas")

                # Guardar en DB
                cursor.execute(
                    """INSERT OR REPLACE INTO auth_2fa (usuario_id, secret, activado) VALUES (?, ?, 1)""",
                    (db_user_id, secret)
                )
                self.db.conn.commit()

                self.bot.reply_to(
                    message,
                    "🔐 Configura la autenticación 2FA en tu app:\n"
                    f"URI: {provisioning_uri}\n"
                    f"O usa este código manual: {secret}\n\n"
                    "Guarda este código en un lugar seguro!",
                    reply_markup=self._get_main_menu()
                )
            except Exception as e:
                self.config.logger.error(f"Error en setup_2fa: {str(e)}")
                self.bot.reply_to(message, "❌ Error al configurar 2FA")

        @self.bot.message_handler(commands=['settings'])
        def show_settings(message):
            try:
                user_id = message.from_user.id
                _ = self._get_user_translation(user_id)

                cursor = self.db.conn.cursor()
                cursor.execute("SELECT lenguaje FROM usuarios WHERE telegram_id = ?", (user_id,))
                current_lang = cursor.fetchone()[0] or self.config.default_lang

                markup = telebot.types.InlineKeyboardMarkup()
                markup.row(
                    telebot.types.InlineKeyboardButton("English", callback_data="setlang_en"),
                    telebot.types.InlineKeyboardButton("Español", callback_data="setlang_es"),
                    telebot.types.InlineKeyboardButton("Português", callback_data="setlang_pt")
                )

                self.bot.reply_to(
                    message,
                    _("⚙️ Configuración actual:\n"
                        "Idioma: {lang}\n"
                        "Selecciona un nuevo idioma:").format(lang=current_lang.upper()),
                    reply_markup=markup
                )
            except Exception as e:
                self.config.logger.error(f"Error en show_settings: {str(e)}")
                self.bot.reply_to(message, "❌ Error al cargar configuración")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('setlang_'))
        def set_language(call):
            try:
                lang = call.data.split('_')[1]
                user_id = call.from_user.id
                _ = self.translations.get(lang, self.translations[self.config.default_lang]).gettext

                if lang in self.config.supported_langs:
                    cursor = self.db.conn.cursor()
                    cursor.execute(
                        "UPDATE usuarios SET lenguaje = ? WHERE telegram_id = ?",
                        (lang, user_id)
                    )
                    self.db.conn.commit()

                    self.bot.answer_callback_query(
                        call.id,
                        _("Idioma cambiado correctamente"),
                        show_alert=True
                    )

                    # Actualizar mensaje
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=_("Configuración actualizada") + f"\nIdioma: {lang.upper()}"
                    )
                else:
                    self.bot.answer_callback_query(
                        call.id,
                        _("Idioma no soportado"),
                        show_alert=True
                    )
            except Exception as e:
                self.config.logger.error(f"Error en set_language: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error al cambiar idioma",
                    show_alert=True
                )

        @self.bot.message_handler(commands=['addnote', 'newnote'])
        def add_note(message):
            try:
                _ = self._get_user_translation(message.from_user.id)
                msg = self.bot.reply_to(
                    message, 
                    _("📝 Envíame el texto de la nota que quieres guardar:"),
                    reply_markup=telebot.types.ReplyKeyboardRemove()
                )
                self.bot.register_next_step_handler(msg, self._process_note_step)
            except Exception as e:
                self.config.logger.error(f"Error en add_note: {str(e)}")
                self.bot.reply_to(
                    message,
                    _("❌ Ocurrió un error al procesar tu nota"),
                    reply_markup=self._get_main_menu()
                )

        @self.bot.message_handler(commands=['listnotes', 'mynotes'])
        def list_notes(message):
            try:
                user_id = message.from_user.id
                _ = self._get_user_translation(user_id)

                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT id, contenido_cifrado, fecha_creacion FROM notas WHERE usuario_id = ?",
                    (db_user_id,)
                )
                notes = cursor.fetchall()

                if not notes:
                    self.bot.reply_to(
                        message, 
                        _("📭 No tienes ninguna nota guardada"),
                        reply_markup=self._get_main_menu()
                    )
                    return

                response = _("📖 *Tus notas:*\n\n")
                for note_id, encrypted_note, fecha in notes:
                    decrypted_note = self.cifrado.descifrar(encrypted_note)
                    short_note = (decrypted_note[:50] + '...') if len(decrypted_note) > 50 else decrypted_note
                    response += _("🆔 {id}\n📅 {date}\n📝 {note}\n\n").format(
                        id=note_id, date=fecha, note=short_note)

                self.bot.reply_to(
                    message,
                    response,
                    parse_mode="Markdown",
                    reply_markup=self._get_main_menu()
                )

            except Exception as e:
                self.config.logger.error(f"Error en list_notes: {str(e)}")
                self.bot.reply_to(
                    message, 
                    _("❌ Error al listar las notas"),
                    reply_markup=self._get_main_menu()
                )

        @self.bot.message_handler(commands=['deletenote', 'delnote'])
        def delete_note(message):
            try:
                user_id = message.from_user.id
                _ = self._get_user_translation(user_id)

                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT id, contenido_cifrado FROM notas WHERE usuario_id = ?",
                    (db_user_id,)
                )
                notes = cursor.fetchall()

                if not notes:
                    self.bot.reply_to(
                        message, 
                        _("📭 No tienes notas para eliminar"),
                        reply_markup=self._get_main_menu()
                    )
                    return

                # Crear teclado con las notas disponibles
                markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True)
                for note_id, encrypted_note in notes:
                    decrypted_note = self.cifrado.descifrar(encrypted_note)
                    short_note = (decrypted_note[:20] + '...') if len(decrypted_note) > 20 else decrypted_note
                    markup.add(f"{note_id}: {short_note}")

                msg = self.bot.reply_to(
                    message, 
                    _("🗑 Selecciona la nota que deseas eliminar:"),
                    reply_markup=markup
                )
                self.bot.register_next_step_handler(msg, self._process_delete_note_step)

            except Exception as e:
                self.config.logger.error(f"Error en delete_note: {str(e)}")
                self.bot.reply_to(
                    message, 
                    _("❌ Error al listar notas para eliminar"),
                    reply_markup=self._get_main_menu()
                )

        @self.bot.message_handler(commands=['addreminder', 'newreminder'])
        def add_reminder(message):
            try:
                _ = self._get_user_translation(message.from_user.id)
                # Verificar si el mensaje incluye parámetros
                if len(message.text.split()) > 1:
                    parts = message.text.split(maxsplit=2)
                    if len(parts) >= 3:
                        text = parts[1]
                        time_part = parts[2]
                        recurrente = "--recurrente" in message.text

                        # Validar formato de hora
                        try:
                            datetime.strptime(time_part, "%H:%M")
                            self._process_reminder_time_step(message, text, recurrente)
                            return
                        except ValueError:
                            pass

                msg = self.bot.reply_to(
                    message,
                    _("⏰ ¿Qué quieres que te recuerde? Envía el texto del recordatorio:"),
                    reply_markup=telebot.types.ReplyKeyboardRemove()
                )
                self.bot.register_next_step_handler(msg, lambda m: self._process_reminder_text_step(m))
            except Exception as e:
                self.config.logger.error(f"Error en add_reminder: {str(e)}")
                self.bot.reply_to(
                    message, 
                    _("❌ Ocurrió un error al crear el recordatorio"),
                    reply_markup=self._get_main_menu()
                )

        @self.bot.message_handler(commands=['listreminders', 'myreminders'])
        def list_reminders(message):
            try:
                user_id = message.from_user.id
                _ = self._get_user_translation(user_id)
                
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                db_user_id = cursor.fetchone()[0]
                
                cursor.execute(
                    """SELECT id, texto, hora_recordatorio, recurrente 
                    FROM recordatorios 
                    WHERE usuario_id = ? AND completado = 0
                    ORDER BY hora_recordatorio""",
                    (db_user_id,)
                )
                reminders = cursor.fetchall()
                
                if not reminders:
                    self.bot.reply_to(
                        message, 
                        _("⏳ No tienes recordatorios pendientes"),
                        reply_markup=self._get_main_menu()
                    )
                    return
                    
                response = _("⏰ *Tus recordatorios pendientes:*\n\n")
                for reminder_id, text, reminder_time, recurrente in reminders:
                    recurrente_text = _("(Recurrente)") if recurrente else ""
                    response += _("🆔 {id}\n⏰ {time} {recurrent}\n📝 {text}\n\n").format(
                        id=reminder_id, time=reminder_time, recurrent=recurrente_text, text=text)
                    
                self.bot.reply_to(
                    message, 
                    response, 
                    parse_mode="Markdown",
                    reply_markup=self._get_main_menu()
                )
                
            except Exception as e:
                self.config.logger.error(f"Error en list_reminders: {str(e)}")
                self.bot.reply_to(
                    message, 
                    _("❌ Error al listar los recordatorios"),
                    reply_markup=self._get_main_menu()
                )

        @self.bot.message_handler(commands=['clearall'])
        def clear_all_data(message):
            try:
                user_id = message.from_user.id
                _ = self._get_user_translation(user_id)
                
                # Confirmación antes de eliminar
                markup = telebot.types.InlineKeyboardMarkup()
                markup.row(
                    telebot.types.InlineKeyboardButton(_("Sí, eliminar todo"), callback_data="confirm_clear"),
                    telebot.types.InlineKeyboardButton(_("Cancelar"), callback_data="cancel_clear")
                )

                self.bot.reply_to(
                    message,
                    _("⚠️ ¿Estás seguro que quieres eliminar TODOS tus datos?\nEsta acción no se puede deshacer."),
                    reply_markup=markup
                )
            except Exception as e:
                self.config.logger.error(f"Error en clear_all_data: {str(e)}")
                self.bot.reply_to(message, _("❌ Error al procesar la solicitud"))

        @self.bot.callback_query_handler(func=lambda call: call.data in ['confirm_clear', 'cancel_clear'])
        def handle_clear_confirmation(call):
            try:
                _ = self._get_user_translation(call.from_user.id)
                
                if call.data == 'confirm_clear':
                    user_id = call.from_user.id
                    cursor = self.db.conn.cursor()
                    cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
                    db_user_id = cursor.fetchone()[0]

                    # Registrar consentimiento de eliminación
                    self.db.registrar_auditoria(
                        db_user_id,
                        "GDPR_DELETE_REQUEST",
                        {"ip": "Telegram", "user_agent": "Telegram"}
                    )

                    # Eliminar todos los datos
                    cursor.execute("DELETE FROM notas WHERE usuario_id = ?", (db_user_id,))
                    cursor.execute("DELETE FROM recordatorios WHERE usuario_id = ?", (db_user_id,))
                    cursor.execute("DELETE FROM auth_2fa WHERE usuario_id = ?", (db_user_id,))
                    cursor.execute("DELETE FROM auditoria WHERE usuario_id = ?", (db_user_id,))
                    cursor.execute("DELETE FROM usuarios WHERE id = ?", (db_user_id,))

                    self.db.conn.commit()

                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=_("♻️ Todos tus datos han sido eliminados según GDPR")
                    )
                else:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=_("✅ Operación cancelada. Tus datos están seguros.")
                    )
            except Exception as e:
                self.db.conn.rollback()
                self.config.logger.error(f"Error en handle_clear_confirmation: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    _("❌ Error al eliminar datos"),
                    show_alert=True
                )

#---------------------
    def _process_note_step(self, message):
        """Procesa el texto de la nota recibido"""
        try:
            user_id = message.from_user.id
            note_text = message.text
            _ = self._get_user_translation(user_id)
            
            if not note_text or len(note_text.strip()) == 0:
                self.bot.reply_to(
                    message, 
                    _("❌ El texto de la nota no puede estar vacío"),
                    reply_markup=self._get_main_menu()
                )
                return
                
            if len(note_text) > 2000:
                self.bot.reply_to(
                    message, 
                    _("❌ La nota es demasiado larga (máximo 2000 caracteres)"),
                    reply_markup=self._get_main_menu()
                )
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
            
            self.bot.reply_to(
                message, 
                _("✅ Nota guardada correctamente"),
                reply_markup=self._get_main_menu()
            )
            
            self.db.registrar_auditoria(
                db_user_id,
                "NOTA_CREADA",
                {"tamaño": len(note_text)}
            )
        except Exception as e:
            self.db.conn.rollback()
            self.config.logger.error(f"Error en _process_note_step: {str(e)}")
            self.bot.reply_to(
                message, 
                _("❌ Error al guardar la nota"),
                reply_markup=self._get_main_menu()
            )

    def _process_delete_note_step(self, message):
        """Procesa la selección de nota a eliminar"""
        try:
            user_id = message.from_user.id
            selected_note = message.text
            _ = self._get_user_translation(user_id)
            
            # Extraer el ID de la nota del texto seleccionado
            note_id = int(selected_note.split(":")[0])
            
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (user_id,))
            db_user_id = cursor.fetchone()[0]
            
            # Verificar que la nota pertenece al usuario antes de eliminar
            cursor.execute(
                "DELETE FROM notas WHERE id = ? AND usuario_id = ?",
                (note_id, db_user_id)
            )
            
            if cursor.rowcount == 0:
                self.bot.reply_to(
                    message, 
                    _("❌ La nota no existe o no tienes permisos para eliminarla"),
                    reply_markup=self._get_main_menu()
                )
                return
                
            self.db.conn.commit()
            
            self.bot.reply_to(
                message, 
                _("✅ Nota {id} eliminada correctamente").format(id=note_id),
                reply_markup=self._get_main_menu()
            )
            
            # Registrar en auditoría
            self.db.registrar_auditoria(
                db_user_id,
                "NOTA_ELIMINADA",
                {"nota_id": note_id}
            )
            
        except ValueError:
            self.bot.reply_to(
                message, 
                _("❌ Formato de selección inválido"),
                reply_markup=self._get_main_menu()
            )
        except Exception as e:
            self.db.conn.rollback()
            self.config.logger.error(f"Error en _process_delete_note_step: {str(e)}")
            self.bot.reply_to(
                message, 
                _("❌ Error al eliminar la nota"),
                reply_markup=self._get_main_menu()
            )

    def _process_reminder_text_step(self, message):
        """Procesa el texto del recordatorio y pide la hora"""
        try:
            if not hasattr(message, 'text') or not message.text:
                self.bot.reply_to(
                    message,
                
                    ("❌ Debes proporcionar un texto para el recordatorio"),
                    reply_markup=self._get_main_menu()
                )
                return
                
            reminder_text = message.text
            
            msg = self.bot.reply_to(
                message,
                ("🕒 ¿A qué hora quieres que te lo recuerde? (Formato HH:MM, ej. 14:30)"),
                    reply_markup=telebot.types.ReplyKeyboardRemove()
            )
            self.bot.register_next_step_handler(
                msg,
                lambda m: self._process_reminder_time_step(m, reminder_text)
            )
        except Exception as e:
            self.config.logger.error(f"Error en _process_reminder_text_step: {str(e)}")
            self.bot.reply_to(
                message,
                ("❌ Ocurrió un error al procesar tu recordatorio"),
                reply_markup=self._get_main_menu()
            )

    def _process_reminder_time_step(self, message, reminder_text, recurrente=False):
        """Procesa la hora del recordatorio y lo guarda"""
        try:
            reminder_time = message.text
            _ = self._get_user_translation(message.from_user.id)
            
            # Validar formato de hora
            try:
                datetime.strptime(reminder_time, "%H:%M")
            except ValueError:
                self.bot.reply_to(
                    message, 
                    _("❌ Formato de hora inválido. Usa HH:MM (ej. 14:30)"),
                    reply_markup=self._get_main_menu()
                )
                return
                
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE telegram_id = ?", (message.from_user.id,))
            db_user_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT INTO recordatorios (usuario_id, texto, hora_recordatorio, recurrente) VALUES (?, ?, ?, ?)",
                (db_user_id, reminder_text, reminder_time, recurrente)
            )
            reminder_id = cursor.lastrowid
            self.db.conn.commit()
            
            self._schedule_reminder(message.from_user.id, reminder_time, reminder_text, reminder_id, recurrente)
            
            self.bot.reply_to(
                message, 
                _("✅ Recordatorio programado para las {time}\n📝 Texto: {text}").format(
                    time=reminder_time, text=reminder_text),
                reply_markup=self._get_main_menu()
            )
            
            self.db.registrar_auditoria(
                db_user_id,
                "RECORDATORIO_CREADO",
                {"hora": reminder_time, "tamaño_texto": len(reminder_text), "recurrente": recurrente}
            )
        except Exception as e:
            self.db.conn.rollback()
            self.config.logger.error(f"Error en _process_reminder_time_step: {str(e)}")
            self.bot.reply_to(
                message, 
                _("❌ Error al programar el recordatorio"),
                reply_markup=self._get_main_menu()
            )

    def run(self):
        """Inicia el bot"""
        self.config.logger.info("Iniciando RecoNotas Secure v2.3 con autenticación 2FA y multiidioma")
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
