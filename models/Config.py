
# ------------------------- CONFIGURACIÓN -------------------------
""" 
Dividiendo las clases para estructurar cada funcion 
"""
import os
import sys
import io
import logging
from pathlib import Path
from dotenv import load_dotenv
import pyotp


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
