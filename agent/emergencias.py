# agent/emergencias.py — Almacen y logica de emergencias
# Generado por AgentKit

"""
Maneja el estado de las emergencias activas de SaveUs.

Guarda en memoria cada emergencia con su ubicacion mas reciente y el historial
de puntos, para que la pagina de seguimiento (/track/{id}) muestre el recorrido
en tiempo real.

Nota: el almacenamiento es en memoria (se pierde al reiniciar el servidor).
Para una emergencia activa es suficiente; si se necesita persistencia se puede
cambiar a SQLite/PostgreSQL mas adelante.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Contacto:
    name: str
    phone: str
    relation: str = ""


@dataclass
class Ubicacion:
    lat: float
    lng: float
    accuracy: float = 0.0
    timestamp: float = field(default_factory=lambda: time.time() * 1000)
    address: str | None = None

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "accuracy": self.accuracy,
            "timestamp": self.timestamp,
            "address": self.address,
        }


@dataclass
class Emergencia:
    id: str
    nombre_usuario: str
    contacts: list[Contacto]
    ubicacion: Ubicacion | None
    estado: str = "activa"  # activa | cancelada
    creada: float = field(default_factory=lambda: time.time() * 1000)
    actualizada: float = field(default_factory=lambda: time.time() * 1000)
    historial: list[Ubicacion] = field(default_factory=list)

    def to_estado_dict(self) -> dict:
        """Datos que consume la pagina de seguimiento."""
        return {
            "id": self.id,
            "nombre_usuario": self.nombre_usuario,
            "estado": self.estado,
            "creada": self.creada,
            "actualizada": self.actualizada,
            "ubicacion": self.ubicacion.to_dict() if self.ubicacion else None,
            "historial": [u.to_dict() for u in self.historial],
        }


# Almacen en memoria: { emergencia_id: Emergencia }
_emergencias: dict[str, Emergencia] = {}


def crear_emergencia(
    id: str,
    nombre_usuario: str,
    contacts: list[Contacto],
    ubicacion: Ubicacion | None,
) -> Emergencia:
    """Registra una nueva emergencia (o reemplaza una previa con el mismo id)."""
    emergencia = Emergencia(
        id=id,
        nombre_usuario=nombre_usuario,
        contacts=contacts,
        ubicacion=ubicacion,
        historial=[ubicacion] if ubicacion else [],
    )
    _emergencias[id] = emergencia
    return emergencia


def obtener_emergencia(id: str) -> Emergencia | None:
    return _emergencias.get(id)


def actualizar_ubicacion(id: str, ubicacion: Ubicacion) -> Emergencia | None:
    """Agrega un nuevo punto de ubicacion a una emergencia activa."""
    emergencia = _emergencias.get(id)
    if not emergencia:
        return None
    emergencia.ubicacion = ubicacion
    emergencia.actualizada = ubicacion.timestamp
    emergencia.historial.append(ubicacion)
    # Limitar el historial para no crecer indefinidamente
    if len(emergencia.historial) > 500:
        emergencia.historial = emergencia.historial[-500:]
    return emergencia


def cancelar_emergencia(id: str) -> Emergencia | None:
    emergencia = _emergencias.get(id)
    if not emergencia:
        return None
    emergencia.estado = "cancelada"
    emergencia.actualizada = time.time() * 1000
    return emergencia
