# agent/providers/base.py — Clase base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define la interfaz comun que todos los proveedores de WhatsApp deben implementar.
Para el caso de SaveUs solo necesitamos enviar mensajes salientes (alertas),
pero la interfaz queda lista por si luego se reciben mensajes entrantes.
"""

from abc import ABC, abstractmethod


def normalizar_telefono(telefono: str) -> str:
    """
    Convierte un numero a formato E.164 que Twilio acepta.
    Quita espacios, guiones y parentesis. Garantiza el prefijo '+'.

    Ej: "+57 319 215 2335" -> "+573192152335"
    """
    if not telefono:
        return ""
    solo_digitos = "".join(c for c in telefono if c.isdigit())
    if not solo_digitos:
        return ""
    return "+" + solo_digitos


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envia un mensaje de texto. Retorna True si fue exitoso."""
        ...
