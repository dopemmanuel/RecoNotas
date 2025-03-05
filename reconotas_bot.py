""" 
Son imports que se necesitan para configurar el bot
"""
import os
import threading
from datetime import datetime
import sqlite3
import time as time_module
from dotenv import load_dotenv
import telebot

# Cargar las variables del archivo .env
load_dotenv()

# Obtener el token de entorno
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Error: No se encontró TELEGRAM_BOT_TOKEN en .env")

print("🔍 Cargando el bot...")

# Inicializar el bot
bot = telebot.TeleBot(API_TOKEN)

# Clase para manejar el estado del bot
class BotState:
    def __init__(self):
        self.activo = True
        self.ultima_interaccion = datetime.now()
        self.inactivo = False

# Crear una instancia del estado del bot
bot_state = BotState()

# Función para crear una nueva conexión a la base de datos
def crear_conexion():
    """Crea una nueva conexión a la base de datos."""
    return sqlite3.connect("reconotas.db", check_same_thread=False)

# Crear la tabla de notas y recordatorios (solo una vez)
def crear_tablas():
    """Crea las tablas necesarias en la base de datos."""
    conn = crear_conexion()
    cursor = conn.cursor()
    
    # Crear la tabla de notas si no existe
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        nota TEXT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_expiracion TIMESTAMP  -- Nueva columna para notas temporales
    );
    """)
    
    # Verificar si la columna fecha_expiracion existe
    cursor.execute("PRAGMA table_info(notas)")
    columnas = cursor.fetchall()
    columnas_existentes = [columna[1] for columna in columnas]  # Nombre de las columnas
    
    if "fecha_expiracion" not in columnas_existentes:
        # Agregar la columna fecha_expiracion si no existe
        cursor.execute("ALTER TABLE notas ADD COLUMN fecha_expiracion TIMESTAMP")
        print("✅ Columna 'fecha_expiracion' añadida a la tabla 'notas'.")
    
    # Crear la tabla de recordatorios si no existe
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recordatorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        mensaje TEXT,
        hora TEXT
    );
    """)
    
    conn.commit()
    conn.close()

# Crear las tablas al inicio
crear_tablas()

# Función para enviar recordatorios
def check_reminders():
    """Envía recordatorios a los usuarios cuando es la hora programada."""
    while bot_state.activo:
        conn = crear_conexion()
        cursor = conn.cursor()
        now = datetime.now().strftime("%H:%M")
        cursor.execute("SELECT user_id, mensaje FROM recordatorios WHERE hora = ?", (now,))
        reminders = cursor.fetchall()
        for reminder in reminders:
            user_id, mensaje = reminder
            try:
                bot.send_message(user_id, f"⏰ Recordatorio: {mensaje}")
                # Eliminar el recordatorio después de enviarlo (opcional)
                cursor.execute("DELETE FROM recordatorios WHERE user_id = ? AND mensaje = ? AND hora = ?", (user_id, mensaje, now))
                conn.commit()
            except telebot.apihelper.ApiException as e:
                print(f"❌ No se pudo enviar el recordatorio a {user_id}: {e}")
        conn.close()
        time_module.sleep(60)  # Revisar cada minuto

# Función para eliminar notas expiradas
def check_expired_notes():
    """Elimina las notas expiradas automáticamente."""
    while bot_state.activo:
        conn = crear_conexion()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM notas WHERE fecha_expiracion <= ?", (now,))
        conn.commit()
        conn.close()
        time_module.sleep(60)  # Revisar cada minuto

# Iniciar el hilo de recordatorios
reminder_thread = threading.Thread(target=check_reminders)
reminder_thread.daemon = True
reminder_thread.start()

# Iniciar el hilo de eliminación de notas expiradas
expired_thread = threading.Thread(target=check_expired_notes)
expired_thread.daemon = True
expired_thread.start()

# Estados para manejar la interacción paso a paso
user_states = {}

# Función para verificar la inactividad
def verificar_inactividad():
    """Verifica si el bot ha estado inactivo durante un tiempo."""
    while bot_state.activo:
        tiempo_inactivo = (datetime.now() - bot_state.ultima_interaccion).total_seconds()
        if tiempo_inactivo > 300 and not bot_state.inactivo:  # 300 segundos = 5 minutos
            bot_state.inactivo = True
            if user_states:  # Verificar si hay usuarios activos
                bot.send_message(list(user_states.keys())[0], "Zzzz...")  # Enviar "Zzzz" al último usuario activo
        time_module.sleep(60)  # Revisar cada minuto

# Iniciar el hilo de verificación de inactividad
inactividad_thread = threading.Thread(target=verificar_inactividad)
inactividad_thread.daemon = True
inactividad_thread.start()

# Comandos del bot
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Envía un mensaje de bienvenida al usuario."""
    bot_state.ultima_interaccion = datetime.now()
    if bot_state.inactivo:
        bot_state.inactivo = False
        bot.reply_to(message, "¡Estoy despierto! 😊")
    bot.reply_to(message, "¡Bienvenido a RecoNotas! Tu asistente personal para notas y recordatorios.")
    bot.reply_to(message, "Escribe /help para ver los comandos")

@bot.message_handler(commands=['help'])
def send_help(message):
    """Muestra una lista de comandos disponibles."""
    bot_state.ultima_interaccion = datetime.now()
    help_text = (
        "/start - Inicia el bot\n"
        "/help - Muestra esta ayuda\n"
        "/addnote - Añade una nueva nota\n"
        "/addtempnote - Añade una nota temporal (se autodestruye después de un tiempo)\n"
        "/listnotes - Lista todas tus notas\n"
        "/deletenote - Elimina una nota\n"
        "/addreminder - Añade un recordatorio\n"
        "/listreminders - Lista todos tus recordatorios\n"
        "/tasks - Muestra todas las tareas y recordatorios pendientes\n"
        "/clearall - Borra todas tus notas y recordatorios\n"
        "/apagar - Apaga el bot"  # Nuevo comando
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['apagar'])
def apagar_bot(message):
    """Apaga el bot de manera segura."""
    bot_state.activo = False
    bot.reply_to(message, "🛑 Bot apagado. ¡Hasta luego!")
    bot.stop_polling()

# Resto de los comandos (addnote, addtempnote, listnotes, deletenote, addreminder, listreminders, clearall)
# ... (Mantén el código existente para estos comandos)

# Iniciar el bot
print("✅ RecoNotas está en línea y esperando mensajes...")
try:
    bot.polling()
except ValueError as e:
    print(f"❌ Error al iniciar el bot: {e}")