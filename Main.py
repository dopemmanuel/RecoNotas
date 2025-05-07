# -*- coding: utf-8 -*-
# Cambio necesario: Ajustar imports
import sys
from models.Config import Config
from core.Bot import RecoNotasBot

# [Código final del archivo original SIN CAMBIOS]
if __name__ == "__main__":
    try:
        config_instance = Config()
        bot = RecoNotasBot(config_instance)
        bot.run()
    except ValueError as e:
        print(f"❌ Error de configuración: {str(e)}")
        print("ℹ️ Asegúrate de tener un archivo .env con todas las variables requeridas")
        sys.exit(1)
    except Exception as e: # pylint: disable=broad-except
        print(f"❌ Error inesperado: {str(e)}")
        sys.exit(1)
