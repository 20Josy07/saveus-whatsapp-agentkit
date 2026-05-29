# agent/providers/twilio.py — Adaptador para Twilio WhatsApp
# Generado por AgentKit

"""
Proveedor de WhatsApp usando Twilio.

Soporta dos formas de autenticacion:
  1. API Key (recomendado): TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET
  2. Auth Token clasico:     TWILIO_AUTH_TOKEN

En ambos casos se necesita TWILIO_ACCOUNT_SID (empieza con "AC") para la URL.
"""

import os
import base64
import logging
import httpx

from agent.providers.base import ProveedorWhatsApp, normalizar_telefono

logger = logging.getLogger("agentkit")


class ProveedorTwilio(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Twilio (API Key o Auth Token)."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.api_key_sid = os.getenv("TWILIO_API_KEY_SID")
        self.api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")
        self.phone_number = normalizar_telefono(os.getenv("TWILIO_PHONE_NUMBER", ""))

    def _credenciales(self) -> tuple[str, str] | None:
        """Devuelve (usuario, password) para la autenticacion Basic de Twilio."""
        if self.api_key_sid and self.api_key_secret:
            return self.api_key_sid, self.api_key_secret
        if self.account_sid and self.auth_token:
            return self.account_sid, self.auth_token
        return None

    def _header_auth(self) -> str | None:
        creds = self._credenciales()
        if not creds:
            return None
        usuario, password = creds
        token = base64.b64encode(f"{usuario}:{password}".encode()).decode()
        return f"Basic {token}"

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envia un mensaje de WhatsApp via Twilio. Retorna True si fue exitoso."""
        auth = self._header_auth()
        if not self.account_sid or not auth or not self.phone_number:
            logger.warning(
                "Twilio mal configurado: falta ACCOUNT_SID, credenciales o PHONE_NUMBER"
            )
            return False

        destino = normalizar_telefono(telefono)
        if not destino:
            logger.warning(f"Numero invalido, se omite: {telefono}")
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        headers = {"Authorization": auth}
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{destino}",
            "Body": mensaje,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(url, data=data, headers=headers)
            if r.status_code == 201:
                logger.info(f"WhatsApp enviado a {destino}")
                return True
            logger.error(f"Error Twilio ({destino}): {r.status_code} — {r.text}")
            return False
        except Exception as e:
            logger.error(f"Excepcion enviando WhatsApp a {destino}: {e}")
            return False
