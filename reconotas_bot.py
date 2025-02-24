from dotenv import load_dotenv
import telebot
import sqlite3
from datetime import datetime


# Cargar las variables del archivo .env
load_dotenv()

# Obtener el token de entorno
API_TOKEN = ""

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

# Comandos del bot
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "¡Bienvenido a RecoNotas! Tu asistente personal para notas y recordatorios.")
    bot.reply_to(message, "Escribe /help para ver los comandos")

    

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "/start - Inicia el bot\n"
        "/help - Muestra esta ayuda\n"
        "/addnote <nota> - Añade una nueva nota\n"
        "/listnotes - Lista todas tus notas\n"
        "/deletenote <id> - Elimina una nota\n"
        "/addreminder <mensaje> <HH:MM> - Añade un recordatorio\n"
        "/listreminders - Lista todos tus recordatorios\n"
        "/tasks - Muestra todas las tareas y recordatorios pendientes\n"
        "/clearall - Borra todas tus notas y recordatorios"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['addnote'])
def add_note(message):
    note = message.text[len('/addnote '):].strip()
    if note:
        user_id = message.from_user.id
        cursor.execute("INSERT INTO notas (user_id, nota) VALUES (?, ?)", (user_id, note))
        conn.commit()
        bot.reply_to(message, "Nota añadida.")
    else:
        bot.reply_to(message, "Por favor, proporciona una nota después del comando.")

@bot.message_handler(commands=['listnotes'])
def list_notes(message):
    user_id = message.from_user.id
    cursor.execute("SELECT id, nota FROM notas WHERE user_id = ?", (user_id,))
    notas = cursor.fetchall()
    if notas:
        response = "📌 Tus notas:\n" + "\n".join([f"{n[0]}. {n[1]}" for n in notas])
    else:
        response = "No tienes notas guardadas."
    bot.reply_to(message, response)

@bot.message_handler(commands=['deletenote'])
def delete_note(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "Formato incorrecto. Usa: /deletenote <id>")
        return
    note_id = int(parts[1])
    user_id = message.from_user.id
    cursor.execute("DELETE FROM notas WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    bot.reply_to(message, "Nota eliminada.")

@bot.message_handler(commands=['addreminder'])
def add_reminder(message):
    try:
        parts = message.text.split(" ", 2)
        if len(parts) < 3:
            raise ValueError("Formato incorrecto")
        user_id = message.from_user.id
        mensaje, hora = parts[1], parts[2]
        datetime.strptime(hora, "%H:%M")  # Validar formato de hora
        cursor.execute("INSERT INTO recordatorios (user_id, mensaje, hora) VALUES (?, ?, ?)", (user_id, mensaje, hora))
        conn.commit()
        bot.reply_to(message, "Recordatorio añadido.")
    except ValueError:
        bot.reply_to(message, "Formato incorrecto. Usa: /addreminder <mensaje> <HH:MM>")

@bot.message_handler(commands=['listreminders'])
def list_reminders(message):
    user_id = message.from_user.id
    cursor.execute("SELECT id, mensaje, hora FROM recordatorios WHERE user_id = ?", (user_id,))
    recordatorios = cursor.fetchall()
    if recordatorios:
        response = "⏰ Tus recordatorios:\n" + "\n".join([f"{r[0]}. {r[1]} a las {r[2]}" for r in recordatorios])
    else:
        response = "No tienes recordatorios guardados."
    bot.reply_to(message, response)

@bot.message_handler(commands=['clearall'])
def clear_all(message):
    user_id = message.from_user.id
    cursor.execute("DELETE FROM notas WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM recordatorios WHERE user_id = ?", (user_id,))
    conn.commit()
    bot.reply_to(message, "Todas tus notas y recordatorios han sido eliminados.")

# Iniciar el bot
print("✅ RecoNotas está en línea y esperando mensajes...")
try:
    bot.polling()
except ValueError as e:
    print(f"❌ Error al iniciar el bot: {e}")
