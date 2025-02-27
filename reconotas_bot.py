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

# Conexión a la base de datos
print("🔗 Conectando a la base de datos...")
conn = sqlite3.connect("reconotas.db", check_same_thread=False)
cursor = conn.cursor()

# Creación de tablas
print("📂 Verificando/creando tablas...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS notas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    nota TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS recordatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    mensaje TEXT,
    hora TEXT
);
""")
conn.commit()

# Índices para mejorar el rendimiento
cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_user_id ON notas (user_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_recordatorios_user_id ON recordatorios (user_id);")
conn.commit()

# Función para enviar recordatorios

def check_reminders():
    """Envía recordatorios a los usuarios cuando es la hora programada."""
    while True:
        now = datetime.now().strftime("%H:%M")
        cursor.execute("SELECT user_id, mensaje FROM recordatorios WHERE hora = ?", (now,))
        reminders = cursor.fetchall()
        for reminder in reminders:
            user_id, mensaje = reminder
            bot.send_message(user_id, f"⏰ Recordatorio: {mensaje}")
        time_module.sleep(60)  # Revisar cada minuto

# Iniciar el hilo de recordatorios
reminder_thread = threading.Thread(target=check_reminders)
reminder_thread.daemon = True
reminder_thread.start()

# Estados para manejar la interacción paso a paso
user_states = {}

# Comandos del bot
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Envía un mensaje de bienvenida al usuario."""
    bot.reply_to(message, "¡Bienvenido a RecoNotas! Tu asistente personal para notas y recordatorios.")
    bot.reply_to(message, "Escribe /help para ver los comandos")

@bot.message_handler(commands=['help'])
def send_help(message):
    """Muestra una lista de comandos disponibles."""
    help_text = (
        "/start - Inicia el bot\n"
        "/help - Muestra esta ayuda\n"
        "/addnote - Añade una nueva nota\n"
        "/listnotes - Lista todas tus notas\n"
        "/deletenote - Elimina una nota\n"
        "/addreminder - Añade un recordatorio\n"
        "/listreminders - Lista todos tus recordatorios\n"
        "/tasks - Muestra todas las tareas y recordatorios pendientes\n"
        "/clearall - Borra todas tus notas y recordatorios"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['addnote'])
def add_note_start(message):
    """Inicia el proceso para añadir una nueva nota."""
    user_id = message.from_user.id
    user_states[user_id] = "waiting_for_note"
    bot.reply_to(message, "📝 Por favor, escribe la nota que deseas añadir:")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_note")
def add_note_finish(message):
    """Guarda la nota proporcionada por el usuario."""
    user_id = message.from_user.id
    note = message.text.strip()
    if note:
        cursor.execute("INSERT INTO notas (user_id, nota) VALUES (?, ?)", (user_id, note))
        conn.commit()
        bot.reply_to(message, "✅ Nota añadida: " + note)
    else:
        bot.reply_to(message, "❌ La nota no puede estar vacía.")
    user_states.pop(user_id, None)

@bot.message_handler(commands=['listnotes'])
def list_notes(message):
    """Lista todas las notas del usuario."""
    try:
        user_id = message.from_user.id
        cursor.execute("SELECT id, nota FROM notas WHERE user_id = ?", (user_id,))
        notas = cursor.fetchall()
        if notas:
            response = "📌 Tus notas:\n" + "\n".join([f"{n[0]}. {n[1]}" for n in notas])
        else:
            response = "No tienes notas guardadas."
        bot.reply_to(message, response)
    except ValueError as e:
        bot.reply_to(message, f"❌ Error al listar las notas: {e}")

@bot.message_handler(commands=['deletenote'])
def delete_note_start(message):
    """Inicia el proceso para eliminar una nota."""
    user_id = message.from_user.id
    cursor.execute("SELECT id, nota FROM notas WHERE user_id = ?", (user_id,))
    notas = cursor.fetchall()
    if notas:
        response = "📌 Selecciona el número de la nota que deseas eliminar:\n" + "\n".join([f"{n[0]}. {n[1]}" for n in notas])
        user_states[user_id] = "waiting_for_note_id_to_delete"
        bot.reply_to(message, response)
    else:
        bot.reply_to(message, "No tienes notas para eliminar.")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_note_id_to_delete")
def delete_note_finish(message):
    """Elimina la nota seleccionada por el usuario."""
    user_id = message.from_user.id
    try:
        note_id = int(message.text.strip())
        cursor.execute("DELETE FROM notas WHERE id = ? AND user_id = ?", (note_id, user_id))
        conn.commit()
        bot.reply_to(message, "✅ Nota eliminada.")
    except ValueError:
        bot.reply_to(message, "❌ Por favor, ingresa un número válido.")
    user_states.pop(user_id, None)

@bot.message_handler(commands=['addreminder'])
def add_reminder_start(message):
    """Inicia el proceso para añadir un recordatorio."""
    user_id = message.from_user.id
    user_states[user_id] = "waiting_for_reminder_message"
    bot.reply_to(message, "⏰ Por favor, escribe el mensaje del recordatorio:")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_reminder_message")
def add_reminder_message(message):
    """Guarda el mensaje del recordatorio y solicita la hora."""
    user_id = message.from_user.id
    user_states[user_id] = {"state": "waiting_for_reminder_time", "mensaje": message.text.strip()}
    bot.reply_to(message, "⏰ Ahora, escribe la hora del recordatorio en formato HH:MM:")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get("state") == "waiting_for_reminder_time")
def add_reminder_finish(message):
    """Inicia el proceso para añadir un recordatorio."""
    user_id = message.from_user.id
    try:
        hora = message.text.strip()
        datetime.strptime(hora, "%H:%M")  # Validar formato de hora
        mensaje = user_states[user_id]["mensaje"]
        cursor.execute("INSERT INTO recordatorios (user_id, mensaje, hora) VALUES (?, ?, ?)", (user_id, mensaje, hora))
        conn.commit()
        bot.reply_to(message, f"✅ Recordatorio añadido: {mensaje} a las {hora}")
    except ValueError:
        bot.reply_to(message, "❌ Formato de hora incorrecto. Usa HH:MM.")
    user_states.pop(user_id, None)

@bot.message_handler(commands=['listreminders'])
def list_reminders(message):
    """Lista todos los recordatorios del usuario."""
    try:
        user_id = message.from_user.id
        cursor.execute("SELECT id, mensaje, hora FROM recordatorios WHERE user_id = ?", (user_id,))
        recordatorios = cursor.fetchall()
        if recordatorios:
            response = "⏰ Tus recordatorios:\n" + "\n".join([f"{r[0]}. {r[1]} a las {r[2]}" for r in recordatorios])
        else:
            response = "No tienes recordatorios guardados."
        bot.reply_to(message, response)
    except ValueError as e:
        bot.reply_to(message, f"❌ Error al listar los recordatorios: {e}")

@bot.message_handler(commands=['clearall'])
def clear_all(message):
    """Elimina todas las notas y recordatorios del usuario."""
    try:
        user_id = message.from_user.id
        cursor.execute("DELETE FROM notas WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM recordatorios WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.reply_to(message, "✅ Todas tus notas y recordatorios han sido eliminados.")
    except ValueError as e:
        bot.reply_to(message, f"❌ Error al borrar todo: {e}")

# Iniciar el bot
print("✅ RecoNotas está en línea y esperando mensajes...")
try:
    bot.polling()
except ValueError as e:
    print(f"❌ Error al iniciar el bot: {e}")
finally:
    conn.close()  # Cerrar la conexión a la base de datos al salir
