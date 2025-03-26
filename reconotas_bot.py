# ------------------------- IMPORTS -------------------------
import os
import re
import sys
import io
import logging
import sqlite3
from datetime import datetime
from threading import Thread
from time import sleep
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

# ------------------------- CONFIGURACIÓN DE ENCODING -------------------------
# Soluciona problemas con emojis en Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ------------------------- CONFIGURACIÓN INICIAL -------------------------
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Error: No se encontró TELEGRAM_BOT_TOKEN en .env")

# Configuración de logging (UTF-8 para soportar emojis)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(API_TOKEN)

# ------------------------- BASE DE DATOS -------------------------
def crear_conexion():
    """Crea y retorna una conexión a la base de datos."""
    return sqlite3.connect("reconotas.db", check_same_thread=False)

def init_db():
    """Inicializa las tablas si no existen."""
    conn = None
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nota TEXT NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recordatorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mensaje TEXT NOT NULL,
            hora TEXT NOT NULL CHECK(hora GLOB '[0-2][0-9]:[0-5][0-9]'),
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_user ON notas (user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recordatorios_user ON recordatorios (user_id)")
        
        conn.commit()
    except sqlite3.Error as e:
        logger.critical("Error al inicializar DB: %s", e)
        raise
    finally:
        if conn:
            conn.close()

init_db()

# ------------------------- RECORDATORIOS CON NOTIFICACIONES -------------------------
def check_reminders():
    """Envía recordatorios con notificaciones push."""
    while True:
        conn = None
        try:
            conn = crear_conexion()
            cursor = conn.cursor()
            now = datetime.now().strftime("%H:%M")
            
            cursor.execute("""
            SELECT user_id, mensaje, id 
            FROM recordatorios 
            WHERE hora = ?
            """, (now,))
            
            for user_id, mensaje, reminder_id in cursor.fetchall():
                try:
                    bot.send_message(
                        user_id,
                        f"🔔 **Recordatorio:** {mensaje}",
                        parse_mode="Markdown",
                        disable_notification=False
                    )
                    cursor.execute("DELETE FROM recordatorios WHERE id = ?", (reminder_id,))
                    conn.commit()
                    logger.info("Notificación enviada a %s", user_id)
                    
                except ApiTelegramException as e:
                    if "chat not found" in str(e).lower():
                        logger.warning("Chat no encontrado (Usuario %s). Eliminando recordatorio...", user_id)
                        cursor.execute("DELETE FROM recordatorios WHERE id = ?", (reminder_id,))
                        conn.commit()
                    else:
                        logger.error("Error de Telegram al enviar notificación a %s: %s", user_id, e)
                except Exception as e:
                    logger.error("Error inesperado al enviar notificación a %s: %s", user_id, e)
        
        except sqlite3.Error as e:
            logger.error("Error de DB en check_reminders: %s", e)
        except Exception as e:
            logger.critical("Error crítico en check_reminders: %s", e)
        finally:
            if conn:
                conn.close()
            sleep(60)

reminder_thread = Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# ------------------------- HANDLERS -------------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Mensaje de bienvenida."""
    try:
        bot.reply_to(
            message,
            "📝 **¡Bienvenido a RecoNotas!**\n\n"
            "🔹 *Comandos disponibles:*\n"
            "/addnote - Añade una nota\n"
            "/listnotes - Lista tus notas\n"
            "/deletenote - Elimina una nota\n"
            "/addreminder - Programa un recordatorio\n"
            "/listreminders - Muestra tus recordatorios\n"
            "/clearall - Borra todo\n"
            "/stop - Apaga el bot temporalmente",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error("Error en send_welcome: %s", e)

@bot.message_handler(commands=['addnote'])
def add_note(message):
    """Inicia el proceso para añadir una nota."""
    try:
        msg = bot.reply_to(message, "📝 *Escribe la nota que deseas guardar:*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_note)
    except Exception as e:
        logger.error("Error en add_note: %s", e)
        bot.reply_to(message, "❌ Error al iniciar la creación de nota.")

def save_note(message):
    """Guarda la nota en la base de datos."""
    user_id = message.from_user.id
    nota = message.text.strip()
    conn = None
    
    try:
        if not nota:
            raise ValueError("La nota no puede estar vacía.")
        
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notas (user_id, nota) VALUES (?, ?)", (user_id, nota))
        conn.commit()
        
        bot.reply_to(message, "✅ *Nota guardada correctamente.*", parse_mode="Markdown")
        logger.info("Nota añadida por %s", user_id)
        
    except ValueError as e:
        bot.reply_to(message, f"❌ {e}")
        logger.warning("ValueError en save_note (Usuario %s): %s", user_id, e)
    except sqlite3.Error as e:
        bot.reply_to(message, "❌ Error al guardar en la base de datos.")
        logger.error("SQLiteError en save_note (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.reply_to(message, "❌ Error inesperado al guardar la nota.")
        logger.critical("Error crítico en save_note (Usuario %s): %s", user_id, e)
    finally:
        if conn:
            conn.close()

@bot.message_handler(commands=['listnotes'])
def list_notes(message):
    """Muestra todas las notas del usuario."""
    user_id = message.from_user.id
    conn = None
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nota FROM notas WHERE user_id = ?", (user_id,))
        notas = cursor.fetchall()
        
        if not notas:
            bot.reply_to(message, "📌 *No tienes notas guardadas.*", parse_mode="Markdown")
            return
        
        markup = InlineKeyboardMarkup()
        for note_id, nota in notas:
            markup.add(InlineKeyboardButton(
                text=f"❌ Eliminar: {nota[:20]}..." if len(nota) > 20 else f"❌ Eliminar: {nota}",
                callback_data=f"delete_note_{note_id}"
            ))
        
        bot.send_message(
            user_id,
            "📌 *Tus notas:*\nUsa los botones para eliminar.",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    except sqlite3.Error as e:
        bot.reply_to(message, "❌ Error al acceder a la base de datos.")
        logger.error("SQLiteError en list_notes (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.reply_to(message, "❌ Error inesperado al listar notas.")
        logger.critical("Error crítico en list_notes (Usuario %s): %s", user_id, e)
    finally:
        if conn:
            conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_note_'))
def delete_note_callback(call):
    """Elimina una nota específica."""
    user_id = call.from_user.id
    note_id = call.data.split('_')[-1]
    conn = None
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notas WHERE id = ? AND user_id = ?", (note_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            raise sqlite3.DatabaseError("La nota no existe o ya fue eliminada.")
        
        bot.answer_callback_query(call.id, "✅ Nota eliminada.")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        logger.info("Nota %s eliminada por %s", note_id, user_id)
        
    except sqlite3.DatabaseError as e:
        bot.answer_callback_query(call.id, "❌ La nota no existe.")
        logger.error("DatabaseError en delete_note (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error al eliminar.")
        logger.critical("Error crítico en delete_note (Usuario %s): %s", user_id, e)
    finally:
        if conn:
            conn.close()

@bot.message_handler(commands=['addreminder'])
def add_reminder_start(message):
    """Inicia el proceso para añadir un recordatorio."""
    try:
        msg = bot.reply_to(message, "⏰ *Escribe el mensaje del recordatorio:*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, add_reminder_message)
    except Exception as e:
        logger.error("Error en add_reminder_start: %s", e)
        bot.reply_to(message, "❌ Error al iniciar la creación de recordatorio.")

def add_reminder_message(message):
    """Guarda el mensaje del recordatorio y solicita la hora."""
    user_id = message.from_user.id
    reminder_text = message.text.strip()
    
    try:
        if not reminder_text:
            raise ValueError("El mensaje no puede estar vacío.")
        
        msg = bot.reply_to(message, "⌛ *Ahora, escribe la hora en formato HH:MM:*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: save_reminder(m, reminder_text))
    except ValueError as e:
        bot.reply_to(message, f"❌ {e}")
        logger.warning("ValueError en add_reminder_message (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.reply_to(message, "❌ Error inesperado.")
        logger.critical("Error crítico en add_reminder_message (Usuario %s): %s", user_id, e)

def save_reminder(message, reminder_text):
    """Guarda el recordatorio en la base de datos."""
    user_id = message.from_user.id
    hora = message.text.strip()
    conn = None
    
    try:
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', hora):
            raise ValueError("Formato de hora inválido. Usa HH:MM (ej. 14:30).")
        
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO recordatorios (user_id, mensaje, hora) VALUES (?, ?, ?)",
            (user_id, reminder_text, hora)
        )
        conn.commit()
        
        bot.reply_to(message, f"✅ *Recordatorio añadido a las {hora}!*", parse_mode="Markdown")
        logger.info("Recordatorio añadido por %s a las %s", user_id, hora)
        
    except ValueError as e:
        bot.reply_to(message, f"❌ {e}")
        logger.warning("ValueError en save_reminder (Usuario %s): %s", user_id, e)
    except sqlite3.IntegrityError as e:
        bot.reply_to(message, "❌ Ya existe un recordatorio a esa hora.")
        logger.error("IntegrityError en save_reminder (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.reply_to(message, "❌ Error inesperado al guardar el recordatorio.")
        logger.critical("Error crítico en save_reminder (Usuario %s): %s", user_id, e)
    finally:
        if conn:
            conn.close()

@bot.message_handler(commands=['listreminders'])
def list_reminders(message):
    """Lista todos los recordatorios del usuario."""
    user_id = message.from_user.id
    conn = None
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, mensaje, hora 
        FROM recordatorios 
        WHERE user_id = ?
        ORDER BY hora
        """, (user_id,))
        
        reminders = cursor.fetchall()
        
        if not reminders:
            bot.reply_to(message, "⏰ *No tienes recordatorios programados.*", parse_mode="Markdown")
            return
        
        response = "⏰ *Tus recordatorios:*\n\n" + "\n".join(
            [f"• {mensaje} a las {hora}" for _, mensaje, hora in reminders]
        )
        
        bot.reply_to(message, response, parse_mode="Markdown")
        
    except sqlite3.Error as e:
        bot.reply_to(message, "❌ Error al acceder a la base de datos.")
        logger.error("SQLiteError en list_reminders (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.reply_to(message, "❌ Error inesperado al listar recordatorios.")
        logger.critical("Error crítico en list_reminders (Usuario %s): %s", user_id, e)
    finally:
        if conn:
            conn.close()

@bot.message_handler(commands=['clearall'])
def clear_all(message):
    """Elimina todas las notas y recordatorios del usuario."""
    user_id = message.from_user.id
    conn = None
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM notas WHERE user_id = ?", (user_id,))
        notes_deleted = cursor.rowcount
        
        cursor.execute("DELETE FROM recordatorios WHERE user_id = ?", (user_id,))
        reminders_deleted = cursor.rowcount
        
        conn.commit()
        
        
        bot.reply_to(
            message,
            f"✅ *Se eliminaron {notes_deleted} notas y {reminders_deleted} recordatorios.*",
            parse_mode="Markdown"
        )
        logger.info("Usuario %s borró %s notas y %s recordatorios", user_id, notes_deleted, reminders_deleted)
        
    except sqlite3.Error as e:
        bot.reply_to(message, "❌ Error al limpiar la base de datos.")
        logger.error("SQLiteError en clear_all (Usuario %s): %s", user_id, e)
    except Exception as e:
        bot.reply_to(message, "❌ Error inesperado al limpiar datos.")
        logger.critical("Error crítico en clear_all (Usuario %s): %s", user_id, e)
    finally:
        if conn:
            conn.close()

@bot.message_handler(commands=['stop'])
def stop_bot(message):
    """Detiene el bot temporalmente."""
    try:
        bot.reply_to(message, "🛑 *Bot pausado. Envía cualquier mensaje para reactivarlo.*", parse_mode="Markdown")
        bot.stop_polling()
    except Exception as e:
        logger.critical("Error al detener el bot: %s", e)

# ------------------------- EJECUCIÓN -------------------------
if __name__ == "__main__":
    try:
        logger.info("✅ Bot iniciado correctamente")
        bot.polling()
    except Exception as e:
        logger.critical("Error en el bucle principal: %s", e)
    finally:
        logger.info("🛑 Bot detenido")
