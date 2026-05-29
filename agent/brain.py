import os
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _cargar_config() -> dict:
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def cargar_system_prompt() -> str:
    return _cargar_config().get(
        "system_prompt",
        "Eres un asistente de emergencia de SaveUs. Responde en español, sé claro y calmado.",
    )


def obtener_mensaje_error() -> str:
    return _cargar_config().get(
        "error_message",
        "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.",
    )


def obtener_mensaje_fallback() -> str:
    return _cargar_config().get(
        "fallback_message",
        "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?",
    )


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    contexto_emergencia: dict | None = None,
) -> str:
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    if contexto_emergencia:
        ub = contexto_emergencia.get("ultima_ubicacion")
        ubicacion_txt = (
            f"https://www.google.com/maps?q={ub['lat']},{ub['lng']}"
            if ub else "No disponible aún"
        )
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        tracking_url = f"{base_url}/alerta/{contexto_emergencia['emergencia_id']}"

        system_prompt += f"""

## ALERTA DE EMERGENCIA ACTIVA — SaveUs

Estás respondiendo a un contacto de emergencia que recibió una notificación SOS.

- Usuario en emergencia: *{contexto_emergencia['nombre_usuario']}*
- Estado: {contexto_emergencia['estado']}
- Activada: {contexto_emergencia['activada_en']}
- Última ubicación GPS: {ubicacion_txt}
- Página de seguimiento en tiempo real: {tracking_url}
- Este contacto: {contexto_emergencia['nombre_contacto']} ({contexto_emergencia['relacion']})

Tu rol ahora es coordinar la respuesta de emergencia:
1. Confirma que recibiste su mensaje y que estás aquí para ayudar.
2. Comparte el link de seguimiento si lo piden.
3. Oriéntalos sobre cómo actuar (llamar al 123, ir a la ubicación, etc.).
4. Mantén la calma y sé claro y directo.
5. Si la emergencia fue cancelada, informa que el usuario está a salvo.
"""

    mensajes = [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes,
        )
        respuesta = response.content[0].text
        logger.info(
            f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)"
        )
        return respuesta
    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
