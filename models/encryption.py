# ------------------------- CIFRADO -------------------------
""" 
Permite cifrar algunos datos sencilbles que el usuario le asigne al bot
"""
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC



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
