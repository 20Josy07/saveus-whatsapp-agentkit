# agent/main.py — Servidor FastAPI de emergencias (SaveUs + WhatsApp)
# Generado por AgentKit

"""
Backend de emergencias para SaveUs.

Flujo:
  SaveUs (boton SOS)
    -> POST /emergencia              : envia WhatsApp a los contactos con link de ubicacion
    -> POST /emergencia/{id}/ubicacion : actualiza la ubicacion en vivo (cada 15s)
    -> POST /emergencia/{id}/cancelar  : marca falsa alarma y avisa a los contactos

  Contactos de emergencia
    -> GET /track/{id}               : pagina web con el mapa en tiempo real
"""

import os
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from agent.providers import obtener_proveedor
from agent import emergencias as store

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
logging.basicConfig(level=logging.DEBUG if ENVIRONMENT == "development" else logging.INFO)
logger = logging.getLogger("agentkit")

PORT = int(os.getenv("PORT", 8000))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}").rstrip("/")

proveedor = obtener_proveedor()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# ── Modelos de entrada (coinciden con services/agentkit.ts de SaveUs) ──────────

class ContactoIn(BaseModel):
    name: str
    phone: str
    relation: str = ""


class UbicacionIn(BaseModel):
    lat: float
    lng: float
    accuracy: float = 0.0
    timestamp: float | None = None
    address: str | None = None


class EmergenciaIn(BaseModel):
    id: str
    nombre_usuario: str
    contacts: list[ContactoIn] = []
    location: UbicacionIn | None = None


class UbicacionUpdate(BaseModel):
    lat: float
    lng: float
    accuracy: float = 0.0
    timestamp: float | None = None


# ── App ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Servidor de emergencias AgentKit en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    logger.info(f"BASE_URL para links de seguimiento: {BASE_URL}")
    yield


app = FastAPI(title="AgentKit — Emergencias SaveUs", version="1.0.0", lifespan=lifespan)

# CORS: la web de SaveUs corre en otro origen (ej: localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_ubicacion(loc: UbicacionIn | UbicacionUpdate | None) -> store.Ubicacion | None:
    if loc is None:
        return None
    datos = loc.model_dump()
    kwargs = {
        "lat": datos["lat"],
        "lng": datos["lng"],
        "accuracy": datos.get("accuracy", 0.0),
        "address": datos.get("address"),
    }
    # Solo pasamos timestamp si viene; si no, el dataclass usa la hora actual
    if datos.get("timestamp"):
        kwargs["timestamp"] = datos["timestamp"]
    return store.Ubicacion(**kwargs)


def _construir_mensaje(nombre: str, tracking_url: str, ubicacion: store.Ubicacion | None) -> str:
    """Mensaje de alerta que reciben los contactos de emergencia."""
    lineas = [
        "🚨 EMERGENCIA — SaveUs",
        "",
        f"{nombre} activó una alerta de emergencia y necesita ayuda urgente.",
    ]
    if ubicacion and ubicacion.address:
        lineas.append(f"📍 {ubicacion.address}")
    lineas.append("")
    lineas.append(f"🗺️ Ubicación en tiempo real:\n{tracking_url}")
    return "\n".join(lineas)


async def _enviar_a_contactos(contactos: list[store.Contacto], mensaje: str) -> int:
    """Envia el mensaje a todos los contactos en paralelo. Retorna cuantos se enviaron."""
    if not contactos:
        return 0
    resultados = await asyncio.gather(
        *(proveedor.enviar_mensaje(c.phone, mensaje) for c in contactos),
        return_exceptions=True,
    )
    return sum(1 for r in resultados if r is True)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "agentkit-emergencias"}


@app.post("/emergencia")
async def activar_emergencia(payload: EmergenciaIn):
    """Activa una emergencia y envia WhatsApp a los contactos con el link de seguimiento."""
    contactos = [store.Contacto(name=c.name, phone=c.phone, relation=c.relation) for c in payload.contacts]
    ubicacion = _to_ubicacion(payload.location)

    store.crear_emergencia(
        id=payload.id,
        nombre_usuario=payload.nombre_usuario,
        contacts=contactos,
        ubicacion=ubicacion,
    )

    tracking_url = f"{BASE_URL}/track/{payload.id}"
    mensaje = _construir_mensaje(payload.nombre_usuario, tracking_url, ubicacion)

    enviados = await _enviar_a_contactos(contactos, mensaje)
    logger.info(f"Emergencia {payload.id}: WhatsApp enviado a {enviados}/{len(contactos)} contactos")

    return {
        "emergencia_id": payload.id,
        "tracking_url": tracking_url,
        "status": "activa",
        "contactos_notificados": enviados,
    }


@app.post("/emergencia/{emergencia_id}/ubicacion")
async def actualizar_ubicacion(emergencia_id: str, loc: UbicacionUpdate):
    """Actualiza la ubicacion en vivo de una emergencia activa."""
    ubicacion = _to_ubicacion(loc)
    emergencia = store.actualizar_ubicacion(emergencia_id, ubicacion)
    if not emergencia:
        raise HTTPException(status_code=404, detail="Emergencia no encontrada")
    return {"status": "ok"}


@app.post("/emergencia/{emergencia_id}/cancelar")
async def cancelar_emergencia(emergencia_id: str):
    """Cancela una emergencia y avisa a los contactos que fue falsa alarma."""
    emergencia = store.cancelar_emergencia(emergencia_id)
    if not emergencia:
        raise HTTPException(status_code=404, detail="Emergencia no encontrada")

    mensaje = (
        "✅ FALSA ALARMA — SaveUs\n\n"
        f"{emergencia.nombre_usuario} canceló la alerta de emergencia. Todo está bien."
    )
    await _enviar_a_contactos(emergencia.contacts, mensaje)
    logger.info(f"Emergencia {emergencia_id} cancelada")
    return {"status": "cancelada"}


@app.get("/emergencia/{emergencia_id}/estado")
async def estado_emergencia(emergencia_id: str):
    """JSON con el estado y ubicacion actual (lo consume la pagina de seguimiento)."""
    emergencia = store.obtener_emergencia(emergencia_id)
    if not emergencia:
        raise HTTPException(status_code=404, detail="Emergencia no encontrada")
    return JSONResponse(emergencia.to_estado_dict())


@app.get("/track/{emergencia_id}", response_class=HTMLResponse)
async def pagina_seguimiento(emergencia_id: str):
    """Pagina web con el mapa en tiempo real que abren los contactos."""
    plantilla = TEMPLATES_DIR / "track.html"
    if not plantilla.exists():
        raise HTTPException(status_code=500, detail="Plantilla de seguimiento no encontrada")
    html = plantilla.read_text(encoding="utf-8")
    html = html.replace("__EMERGENCIA_ID__", emergencia_id)
    return HTMLResponse(html)
