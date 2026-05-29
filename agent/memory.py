import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Float, select, Integer, update
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ── Conversaciones de chat ────────────────────────────────────────────────────

class Mensaje(Base):
    __tablename__ = "mensajes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Emergencias SaveUs ────────────────────────────────────────────────────────

class Emergencia(Base):
    __tablename__ = "emergencias"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nombre_usuario: Mapped[str] = mapped_column(String(100), default="Usuario SaveUs")
    estado: Mapped[str] = mapped_column(String(20), default="activa")  # activa | cancelada
    lat_inicio: Mapped[float] = mapped_column(Float, nullable=True)
    lng_inicio: Mapped[float] = mapped_column(Float, nullable=True)
    direccion_inicio: Mapped[str] = mapped_column(Text, nullable=True)
    activada_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cancelada_en: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class UbicacionEmergencia(Base):
    __tablename__ = "ubicaciones_emergencia"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emergencia_id: Mapped[str] = mapped_column(String(36), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    accuracy: Mapped[float] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContactoNotificado(Base):
    __tablename__ = "contactos_notificados"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emergencia_id: Mapped[str] = mapped_column(String(36), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    relacion: Mapped[str] = mapped_column(String(100))
    notificado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Init ──────────────────────────────────────────────────────────────────────

async def inicializar_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Mensajes de conversación ──────────────────────────────────────────────────

async def guardar_mensaje(telefono: str, role: str, content: str):
    async with async_session() as session:
        session.add(Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
        ))
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = list(reversed(result.scalars().all()))
        return [{"role": m.role, "content": m.content} for m in mensajes]


# ── Emergencias ───────────────────────────────────────────────────────────────

async def guardar_emergencia(
    emergencia_id: str,
    nombre_usuario: str,
    lat: float | None = None,
    lng: float | None = None,
    direccion: str | None = None,
):
    async with async_session() as session:
        session.add(Emergencia(
            id=emergencia_id,
            nombre_usuario=nombre_usuario,
            estado="activa",
            lat_inicio=lat,
            lng_inicio=lng,
            direccion_inicio=direccion,
            activada_en=datetime.utcnow(),
        ))
        await session.commit()


async def obtener_emergencia(emergencia_id: str) -> dict | None:
    async with async_session() as session:
        result = await session.execute(
            select(Emergencia).where(Emergencia.id == emergencia_id)
        )
        e = result.scalar_one_or_none()
        if not e:
            return None

        # Última ubicación
        ub_result = await session.execute(
            select(UbicacionEmergencia)
            .where(UbicacionEmergencia.emergencia_id == emergencia_id)
            .order_by(UbicacionEmergencia.timestamp.desc())
            .limit(1)
        )
        ub = ub_result.scalar_one_or_none()

        return {
            "id": e.id,
            "nombre_usuario": e.nombre_usuario,
            "estado": e.estado,
            "lat_inicio": e.lat_inicio,
            "lng_inicio": e.lng_inicio,
            "direccion_inicio": e.direccion_inicio,
            "activada_en": e.activada_en.isoformat() if e.activada_en else None,
            "cancelada_en": e.cancelada_en.isoformat() if e.cancelada_en else None,
            "ultima_ubicacion": {
                "lat": ub.lat,
                "lng": ub.lng,
                "accuracy": ub.accuracy,
                "timestamp": ub.timestamp.isoformat(),
            } if ub else None,
        }


async def guardar_ubicacion_emergencia(
    emergencia_id: str,
    lat: float,
    lng: float,
    accuracy: float | None = None,
):
    async with async_session() as session:
        session.add(UbicacionEmergencia(
            emergencia_id=emergencia_id,
            lat=lat,
            lng=lng,
            accuracy=accuracy,
            timestamp=datetime.utcnow(),
        ))
        await session.commit()


async def cancelar_emergencia_en_db(emergencia_id: str):
    async with async_session() as session:
        await session.execute(
            update(Emergencia)
            .where(Emergencia.id == emergencia_id)
            .values(estado="cancelada", cancelada_en=datetime.utcnow())
        )
        await session.commit()


async def guardar_contacto_notificado(
    emergencia_id: str,
    nombre: str,
    telefono: str,
    relacion: str,
):
    # Limpiar teléfono para búsqueda consistente
    telefono_limpio = telefono.replace(" ", "").replace("-", "")
    async with async_session() as session:
        session.add(ContactoNotificado(
            emergencia_id=emergencia_id,
            nombre=nombre,
            telefono=telefono_limpio,
            relacion=relacion,
            notificado_en=datetime.utcnow(),
        ))
        await session.commit()


async def obtener_emergencias_activas_por_telefono(telefono: str) -> list[dict]:
    """Busca emergencias activas donde este teléfono fue notificado."""
    telefono_limpio = "+" + telefono.replace("+", "").replace(" ", "").replace("-", "")
    variantes = [telefono_limpio, telefono_limpio.lstrip("+")]

    async with async_session() as session:
        resultados = []
        for variante in variantes:
            q = await session.execute(
                select(ContactoNotificado, Emergencia)
                .join(Emergencia, ContactoNotificado.emergencia_id == Emergencia.id)
                .where(
                    ContactoNotificado.telefono == variante,
                    Emergencia.estado == "activa",
                )
                .order_by(Emergencia.activada_en.desc())
                .limit(1)
            )
            row = q.first()
            if row:
                contacto, emergencia = row
                # Última ubicación
                ub_q = await session.execute(
                    select(UbicacionEmergencia)
                    .where(UbicacionEmergencia.emergencia_id == emergencia.id)
                    .order_by(UbicacionEmergencia.timestamp.desc())
                    .limit(1)
                )
                ub = ub_q.scalar_one_or_none()
                resultados.append({
                    "emergencia_id": emergencia.id,
                    "nombre_usuario": emergencia.nombre_usuario,
                    "estado": emergencia.estado,
                    "activada_en": emergencia.activada_en.isoformat(),
                    "direccion_inicio": emergencia.direccion_inicio,
                    "nombre_contacto": contacto.nombre,
                    "relacion": contacto.relacion,
                    "ultima_ubicacion": {
                        "lat": ub.lat,
                        "lng": ub.lng,
                    } if ub else None,
                })
                break
        return resultados
