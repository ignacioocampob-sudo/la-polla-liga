"""
LA POLLA - LIGA ESPAÑOLA (Streamlit)
====================================
Sistema de quinielas con integración de API de Football-Data.org
"""

import streamlit as st
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime,
    Boolean, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from typing import Optional, List
import requests
import time
import pandas as pd
import os
import sqlite3

# Configuración de página
st.set_page_config(
    page_title="⚽ La Polla - Liga Española",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
        border-bottom: 3px solid #1f77b4;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #1f77b4;
    }
    .tipo-card {
        padding: 18px 12px;
        border-radius: 12px;
        border: 2px solid #ddd;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s;
        background: #fff;
    }
    .tipo-card.activo {
        border-color: #1f77b4;
        background: #e8f0fe;
        box-shadow: 0 2px 8px rgba(31,119,180,0.25);
    }
    .saldo-box {
        background: linear-gradient(135deg, #1f77b4, #2ca02c);
        color: #fff;
        padding: 14px 24px;
        border-radius: 12px;
        text-align: center;
    }
    .saldo-box h3 { margin: 0 0 4px; font-size: 1rem; opacity: 0.85; }
    .saldo-box h1 { margin: 0; font-size: 2rem; }
    .apuesta-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.82em;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

Base = declarative_base()

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

API_CONFIG = {
    "key": "2b4591bb017e438f9fd6af65f09a1085",
    "base_url": "https://api.football-data.org/v4",
    "competition": "PD",
}

TEMPORADA = "2025-2026"
PUNTOS_INICIALES = 100
OPCIONES_APUESTA = [5, 10, 15, 20]

# Multiplicadores / bonus por tipo
REGLAS = {
    "resultado":   {"label": "Resultado",          "mult": 2, "desc": "Predice si gana local, empate o visitante.  Acierto → apuestado × 2"},
    "marcador":    {"label": "Marcador Exacto",    "mult": 3, "desc": "Adivina el marcador exacto (ej. 2-1).  Acierto → apuestado × 3"},
    "goles_total": {"label": "Total de Goles",     "bonus": 5, "desc": "¿Habrá 2 o menos goles (Bajo) o 3 o más (Alto)?  Acierto → apuestado + 5"},
}


# =============================================================================
# MODELOS ORM
# =============================================================================

class Equipo(Base):
    __tablename__ = 'equipos'
    id              = Column(Integer, primary_key=True)
    nombre          = Column(String(100), nullable=False, unique=True)
    nombre_corto    = Column(String(5),   nullable=False, unique=True)
    estadio         = Column(String(100))
    partidos_local      = relationship("Partido", foreign_keys="Partido.equipo_local_id",      back_populates="equipo_local")
    partidos_visitante  = relationship("Partido", foreign_keys="Partido.equipo_visitante_id",  back_populates="equipo_visitante")


class Jornada(Base):
    __tablename__ = 'jornadas'
    id        = Column(Integer, primary_key=True)
    numero    = Column(Integer, nullable=False)
    temporada = Column(String(10), nullable=False)
    cerrada   = Column(Boolean, default=False)
    partidos  = relationship("Partido", back_populates="jornada")
    __table_args__ = (UniqueConstraint('numero', 'temporada', name='uq_jornada_temporada'),)

    @property
    def total_partidos(self):
        return len(self.partidos)


class Partido(Base):
    __tablename__ = 'partidos'
    id                  = Column(Integer, primary_key=True)
    jornada_id          = Column(Integer, ForeignKey('jornadas.id'),  nullable=False)
    equipo_local_id     = Column(Integer, ForeignKey('equipos.id'),   nullable=False)
    equipo_visitante_id = Column(Integer, ForeignKey('equipos.id'),   nullable=False)
    fecha_hora          = Column(DateTime, nullable=False)
    goles_local         = Column(Integer)
    goles_visitante     = Column(Integer)
    estado              = Column(String(20), default='programado')

    jornada         = relationship("Jornada", back_populates="partidos")
    equipo_local    = relationship("Equipo", foreign_keys=[equipo_local_id],    back_populates="partidos_local")
    equipo_visitante= relationship("Equipo", foreign_keys=[equipo_visitante_id], back_populates="partidos_visitante")
    apuestas        = relationship("Apuesta", back_populates="partido")

    @property
    def resultado(self) -> str:
        if self.goles_local is None or self.goles_visitante is None:
            return '-'
        if self.goles_local > self.goles_visitante:  return '1'
        if self.goles_local < self.goles_visitante:  return '2'
        return 'X'

    @property
    def marcador(self) -> str:
        if self.goles_local is None:
            return "vs"
        return f"{self.goles_local}-{self.goles_visitante}"

    @property
    def goles_totales(self) -> Optional[int]:
        if self.goles_local is None:
            return None
        return self.goles_local + self.goles_visitante


class Usuario(Base):
    __tablename__ = 'usuarios'
    id              = Column(Integer, primary_key=True)
    nombre          = Column(String(50),  nullable=False)
    apellidos       = Column(String(100), nullable=False)
    fecha_registro  = Column(DateTime, default=datetime.now)
    activo          = Column(Boolean, default=True)
    apuestas        = relationship("Apuesta", back_populates="usuario")
    puntajes        = relationship("Puntaje", back_populates="usuario")

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellidos}"


class Apuesta(Base):
    """
    tipos: 'resultado' | 'marcador' | 'goles_total'
    prediccion:
        resultado  → '1' | 'X' | '2'
        marcador   → 'L-V'  (ej '2-1')
        goles_total→ 'bajo' | 'alto'   (bajo = ≤2, alto = ≥3)
    """
    __tablename__ = 'apuestas'
    id                      = Column(Integer, primary_key=True)
    usuario_id              = Column(Integer, ForeignKey('usuarios.id'),  nullable=False)
    partido_id              = Column(Integer, ForeignKey('partidos.id'),  nullable=False)
    tipo_apuesta            = Column(String(20), nullable=False)          # resultado | marcador | goles_total
    prediccion              = Column(String(10), nullable=False)
    puntos_apostados        = Column(Integer, nullable=False)             # 5 | 10 | 15 | 20
    puntos_obtenidos        = Column(Integer)                             # NULL = sin procesar
    fecha_apuesta           = Column(DateTime, default=datetime.now)

    usuario = relationship("Usuario", back_populates="apuestas")
    partido = relationship("Partido", back_populates="apuestas")

    __table_args__ = (
        UniqueConstraint('usuario_id', 'partido_id', 'tipo_apuesta', name='uq_usuario_partido_tipo'),
    )

    # ── lógica de acierto ──────────────────────────────────────
    @property
    def acerto(self) -> Optional[bool]:
        p = self.partido
        if p.estado != 'finalizado':
            return None

        if self.tipo_apuesta == 'resultado':
            return self.prediccion == p.resultado

        if self.tipo_apuesta == 'marcador':
            return self.prediccion == f"{p.goles_local}-{p.goles_visitante}"

        if self.tipo_apuesta == 'goles_total':
            total = p.goles_totales
            if self.prediccion == 'bajo':
                return total <= 2
            return total >= 3          # alto

        return None

    def calcular_puntos(self) -> int:
        """Calcula y persiste puntos_obtenidos. Retorna ganancia neta."""
        if self.acerto is None:
            return 0
        if not self.acerto:
            self.puntos_obtenidos = 0
            return -self.puntos_apostados   # pierde lo apostado

        regla = REGLAS[self.tipo_apuesta]
        if 'mult' in regla:
            ganancia = self.puntos_apostados * regla['mult']
        else:
            ganancia = self.puntos_apostados + regla['bonus']

        self.puntos_obtenidos = ganancia
        return ganancia - self.puntos_apostados   # neta = ganancia - costo


class Puntaje(Base):
    """Saldo acumulado del usuario en una temporada."""
    __tablename__ = 'puntajes'
    id                  = Column(Integer, primary_key=True)
    usuario_id          = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    temporada           = Column(String(10), nullable=False)
    puntos_totales      = Column(Integer, default=PUNTOS_INICIALES)   # saldo actual
    aciertos            = Column(Integer, default=0)
    fallos              = Column(Integer, default=0)
    partidos_apostados  = Column(Integer, default=0)
    usuario             = relationship("Usuario", back_populates="puntajes")
    __table_args__ = (UniqueConstraint('usuario_id', 'temporada', name='uq_usuario_temporada'),)

    @property
    def porcentaje_aciertos(self) -> float:
        if self.partidos_apostados == 0:
            return 0.0
        return (self.aciertos / self.partidos_apostados) * 100


# =============================================================================
# GESTOR DE LA LIGA
# =============================================================================

class GestorLiga:

    def __init__(self, db_url: str = "sqlite:///la_polla.db"):
        self.engine = create_engine(db_url, echo=False)
        self._verificar_y_migrar_bd()
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    # ── migración automática ───────────────────────────────────
    def _verificar_y_migrar_bd(self):
        db_path = self.engine.url.database
        if not db_path or not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(db_path)
            cur  = conn.cursor()

            # Si la tabla apuestas existe pero no tiene 'tipo_apuesta' → estructura antigua, drop todo
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apuestas'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(apuestas)")
                cols = [c[1] for c in cur.fetchall()]
                if 'tipo_apuesta' not in cols:
                    for t in ('apuestas','puntajes','partidos','jornadas','usuarios','equipos'):
                        cur.execute(f"DROP TABLE IF EXISTS {t}")
                    conn.commit()

            # Si partidos existe pero falta equipo_local_id → drop
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='partidos'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(partidos)")
                cols = [c[1] for c in cur.fetchall()]
                if 'equipo_local_id' not in cols:
                    for t in ('apuestas','puntajes','partidos','jornadas','usuarios','equipos'):
                        cur.execute(f"DROP TABLE IF EXISTS {t}")
                    conn.commit()

            conn.close()
        except Exception:
            pass

    # ── API ────────────────────────────────────────────────────
    # NOTA: Funciones de API comentadas para deploy en Streamlit Cloud
    # (límite de requests alcanzado en football-data.org)
    
    def cargar_equipos_desde_api(self) -> int:
        """Función deshabilitada - usar carga de datos demo."""
        st.info("ℹ️ Cargando equipos de La Liga (datos demo)...")
        return self._cargar_equipos_demo()
    
    def _cargar_equipos_demo(self) -> int:
        """Carga equipos de La Liga de forma local (sin API)."""
        equipos_demo = [
            {"id": 81, "nombre": "FC Barcelona", "corto": "BAR", "estadio": "Spotify Camp Nou"},
            {"id": 86, "nombre": "Real Madrid CF", "corto": "RMA", "estadio": "Santiago Bernabéu"},
            {"id": 78, "nombre": "Club Atlético de Madrid", "corto": "ATM", "estadio": "Cívitas Metropolitano"},
            {"id": 92, "nombre": "Real Sociedad de Fútbol", "corto": "RSO", "estadio": "Reale Arena"},
            {"id": 94, "nombre": "Villarreal CF", "corto": "VIL", "estadio": "Estadio de la Cerámica"},
            {"id": 77, "nombre": "Athletic Club", "corto": "ATH", "estadio": "San Mamés"},
            {"id": 90, "nombre": "Real Betis Balompié", "corto": "BET", "estadio": "Benito Villamarín"},
            {"id": 558, "nombre": "RC Celta de Vigo", "corto": "CEL", "estadio": "Abanca-Balaídos"},
            {"id": 89, "nombre": "RCD Mallorca", "corto": "MLL", "estadio": "Visit Mallorca Estadi"},
            {"id": 82, "nombre": "Getafe CF", "corto": "GET", "estadio": "Coliseum Alfonso Pérez"},
            {"id": 79, "nombre": "CA Osasuna", "corto": "OSA", "estadio": "El Sadar"},
            {"id": 87, "nombre": "Rayo Vallecano de Madrid", "corto": "RAY", "estadio": "Campo de Fútbol de Vallecas"},
            {"id": 95, "nombre": "Valencia CF", "corto": "VAL", "estadio": "Mestalla"},
            {"id": 559, "nombre": "Sevilla FC", "corto": "SEV", "estadio": "Ramón Sánchez-Pizjuán"},
            {"id": 263, "nombre": "Deportivo Alavés", "corto": "ALA", "estadio": "Mendizorroza"},
            {"id": 275, "nombre": "UD Las Palmas", "corto": "LPA", "estadio": "Estadio de Gran Canaria"},
            {"id": 264, "nombre": "RCD Espanyol de Barcelona", "corto": "ESP", "estadio": "RCDE Stadium"},
            {"id": 298, "nombre": "Girona FC", "corto": "GIR", "estadio": "Montilivi"},
            {"id": 285, "nombre": "CD Leganés", "corto": "LEG", "estadio": "Butarque"},
            {"id": 250, "nombre": "Real Valladolid CF", "corto": "VLL", "estadio": "José Zorrilla"},
        ]
        self.session.query(Equipo).delete()
        self.session.commit()
        for eq in equipos_demo:
            self.session.add(Equipo(
                id=eq['id'],
                nombre=eq['nombre'],
                nombre_corto=eq['corto'],
                estadio=eq['estadio']
            ))
        self.session.commit()
        return len(equipos_demo)

    def cargar_partidos_desde_api(self, jornada_id: int) -> int:
        """Función deshabilitada - usar carga manual."""
        st.warning("⚠️ La carga desde API está deshabilitada. Cree partidos manualmente.")
        return 0

    # ── Equipos ────────────────────────────────────────────────
    def listar_equipos(self) -> List[Equipo]:
        return self.session.query(Equipo).order_by(Equipo.nombre).all()

    # ── Usuarios ───────────────────────────────────────────────
    def insertar_usuario(self, nombre: str, apellidos: str) -> Usuario:
        u = Usuario(nombre=nombre, apellidos=apellidos)
        self.session.add(u)
        self.session.commit()
        return u

    def listar_usuarios(self) -> List[Usuario]:
        return self.session.query(Usuario).filter_by(activo=True).all()

    # ── Jornadas ───────────────────────────────────────────────
    def crear_jornada(self, numero: int, temporada: str) -> Jornada:
        j = Jornada(numero=numero, temporada=temporada)
        self.session.add(j); self.session.commit()
        return j

    def obtener_jornada(self, numero: int, temporada: str) -> Optional[Jornada]:
        return self.session.query(Jornada).filter_by(numero=numero, temporada=temporada).first()

    def listar_jornadas(self, temporada: str) -> List[Jornada]:
        return self.session.query(Jornada).filter_by(temporada=temporada).order_by(Jornada.numero).all()

    # ── Partidos ───────────────────────────────────────────────
    def obtener_partidos_jornada(self, jornada_id: int) -> List[Partido]:
        return self.session.query(Partido).filter_by(jornada_id=jornada_id).order_by(Partido.fecha_hora).all()

    def actualizar_resultado(self, partido_id: int, gl: int, gv: int):
        p = self.session.query(Partido).filter_by(id=partido_id).first()
        if p:
            p.goles_local = gl; p.goles_visitante = gv; p.estado = 'finalizado'
            self.session.commit()

    # ── Puntaje / Saldo ────────────────────────────────────────
    def obtener_o_crear_puntaje(self, usuario_id: int, temporada: str) -> Puntaje:
        p = self.session.query(Puntaje).filter_by(usuario_id=usuario_id, temporada=temporada).first()
        if not p:
            p = Puntaje(usuario_id=usuario_id, temporada=temporada, puntos_totales=PUNTOS_INICIALES)
            self.session.add(p)
            self.session.commit()
        return p

    def puntos_comprometidos(self, usuario_id: int, temporada: str) -> int:
        """Suma de puntos_apostados de apuestas pendientes (partido no finalizado, no procesadas)."""
        return self.session.query(
            pd_func_sum(Apuesta.puntos_apostados)
        ).join(Partido).filter(
            Apuesta.usuario_id == usuario_id,
            Partido.estado != 'finalizado',
            Apuesta.puntos_obtenidos == None
        ).scalar() or 0

    def saldo_disponible(self, usuario_id: int, temporada: str) -> int:
        puntaje = self.obtener_o_crear_puntaje(usuario_id, temporada)
        comprometidos = self.puntos_comprometidos(usuario_id, temporada)
        return puntaje.puntos_totales - comprometidos

    # ── Apuestas ───────────────────────────────────────────────
    def hacer_apuesta(self, usuario_id: int, partido_id: int,
                      tipo: str, prediccion: str, puntos_apostados: int) -> Apuesta:
        # validar saldo
        disponible = self.saldo_disponible(usuario_id, TEMPORADA)
        if puntos_apostados > disponible:
            raise ValueError(f"Saldo insuficiente. Disponible: {disponible} pts")

        # upsert
        ap = self.session.query(Apuesta).filter_by(
            usuario_id=usuario_id, partido_id=partido_id, tipo_apuesta=tipo
        ).first()
        if ap:
            ap.prediccion       = prediccion
            ap.puntos_apostados = puntos_apostados
            ap.fecha_apuesta    = datetime.now()
            ap.puntos_obtenidos = None
        else:
            ap = Apuesta(
                usuario_id=usuario_id, partido_id=partido_id,
                tipo_apuesta=tipo, prediccion=prediccion,
                puntos_apostados=puntos_apostados
            )
            self.session.add(ap)
        self.session.commit()
        return ap

    # ── Clasificación ──────────────────────────────────────────
    def obtener_clasificacion(self, temporada: str) -> List[Puntaje]:
        return self.session.query(Puntaje).filter_by(temporada=temporada).order_by(
            Puntaje.puntos_totales.desc(), Puntaje.aciertos.desc()
        ).all()

    # ── Procesar jornada ───────────────────────────────────────
    def procesar_jornada(self, jornada_id: int, temporada: str) -> dict:
        resumen = {'apuestas_procesadas': 0, 'puntos_otorgados': 0, 'puntos_perdidos': 0}

        apuestas = self.session.query(Apuesta).join(Partido).filter(
            Partido.jornada_id == jornada_id,
            Partido.estado == 'finalizado',
            Apuesta.puntos_obtenidos == None
        ).all()

        for ap in apuestas:
            neta = ap.calcular_puntos()   # actualiza puntos_obtenidos, retorna neta

            puntaje = self.obtener_o_crear_puntaje(ap.usuario_id, temporada)
            puntaje.puntos_totales += neta
            puntaje.partidos_apostados += 1

            if ap.acerto:
                puntaje.aciertos += 1
                resumen['puntos_otorgados'] += neta
            else:
                puntaje.fallos += 1
                resumen['puntos_perdidos'] += ap.puntos_apostados

            resumen['apuestas_procesadas'] += 1

        self.session.commit()
        return resumen

    def cerrar(self):
        self.session.close()


# helper para la consulta de suma
from sqlalchemy import func as sa_func
pd_func_sum = sa_func.coalesce(sa_func.sum(Apuesta.puntos_apostados), 0).__class__
# redefine limpio
def _sum_col(col):
    return sa_func.coalesce(sa_func.sum(col), 0)


# Parcheamos puntos_comprometidos para usar la función correcta
def _puntos_comprometidos(self, usuario_id, temporada):
    from sqlalchemy import func as _f
    return self.session.query(
        _f.coalesce(_f.sum(Apuesta.puntos_apostados), 0)
    ).join(Partido).filter(
        Apuesta.usuario_id == usuario_id,
        Partido.estado != 'finalizado',
        Apuesta.puntos_obtenidos == None
    ).scalar()

GestorLiga.puntos_comprometidos = _puntos_comprometidos


# =============================================================================
# INICIALIZACIÓN
# =============================================================================

@st.cache_resource
def get_gestor():
    g = GestorLiga()
    if not g.listar_usuarios():
        g.insertar_usuario("Demo", "Usuario")
    return g


# =============================================================================
# INTERFAZ – MAIN / NAV
# =============================================================================

def main():
    st.markdown('<div class="main-header">⚽ LA POLLA - LIGA ESPAÑOLA</div>', unsafe_allow_html=True)
    gestor = get_gestor()

    st.sidebar.title("📋 Menú Principal")
    st.sidebar.markdown("---")

    menu = {
        "🏠 Dashboard":        "dashboard",
        "⚽ Equipos":          "equipos",
        "👥 Usuarios":         "usuarios",
        "📅 Jornadas":         "jornadas",
        "🎯 Hacer Apuestas":   "apuestas",
        "📊 Clasificación":    "clasificacion",
        "⚙️ Administración":   "admin",
    }
    page = menu[st.sidebar.radio("Ir a:", list(menu.keys()))]
    st.sidebar.markdown("---")
    st.sidebar.info(f"**Temporada:** {TEMPORADA}")

    pages = {
        "dashboard":     show_dashboard,
        "equipos":       show_equipos,
        "usuarios":      show_usuarios,
        "jornadas":      show_jornadas,
        "apuestas":      show_apuestas,
        "clasificacion": show_clasificacion,
        "admin":         show_admin,
    }
    pages[page](gestor)


# =============================================================================
# PÁGINAS
# =============================================================================

def show_dashboard(gestor):
    st.header("📊 Dashboard General")
    equipos       = gestor.listar_equipos()
    usuarios      = gestor.listar_usuarios()
    jornadas      = gestor.listar_jornadas(TEMPORADA)
    clasificacion = gestor.obtener_clasificacion(TEMPORADA)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⚽ Equipos",  len(equipos))
    c2.metric("👥 Usuarios", len(usuarios))
    c3.metric("📅 Jornadas", len(jornadas))
    if clasificacion:
        lider = clasificacion[0]
        c4.metric("🏆 Líder", lider.usuario.nombre_completo, f"{lider.puntos_totales} pts")
    else:
        c4.metric("🏆 Líder", "Sin datos")

    st.markdown("---")

    if clasificacion:
        st.subheader("🏆 Top 5 Clasificación")
        rows = []
        for i, p in enumerate(clasificacion[:5], 1):
            rows.append({"Pos": f"#{i}", "Usuario": p.usuario.nombre_completo,
                         "Saldo (pts)": p.puntos_totales, "Aciertos": p.aciertos,
                         "Fallos": p.fallos, "% Acierto": f"{p.porcentaje_aciertos:.1f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("📋 No hay datos de clasificación aún.")

    st.markdown("---")
    st.subheader("📅 Jornadas Recientes")
    if jornadas:
        rows = [{"Jornada": f"#{j.numero}", "Temporada": j.temporada,
                 "Partidos": j.total_partidos,
                 "Estado": "✅ Cerrada" if j.cerrada else "🔓 Abierta"} for j in jornadas[-5:]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("📋 No hay jornadas registradas.")


# ── equipos ────────────────────────────────────────────────────────────────

def show_equipos(gestor):
    st.header("⚽ Equipos de La Liga")
    equipos = gestor.listar_equipos()
    if not equipos:
        st.warning("⚠️ No hay equipos. Ve a Administración → Cargar desde API.")
        return
    search = st.text_input("🔍 Buscar equipo", placeholder="Nombre…")
    if search:
        equipos = [e for e in equipos if search.lower() in e.nombre.lower()]
    cols = st.columns(3)
    for i, e in enumerate(equipos):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="metric-card">
                <h3>{e.nombre}</h3>
                <p><strong>Código:</strong> {e.nombre_corto}</p>
                <p>🏟️ {e.estadio or 'Sin estadio'}</p>
            </div><br>""", unsafe_allow_html=True)
    st.info(f"📊 Total: {len(equipos)} equipos")


# ── usuarios ───────────────────────────────────────────────────────────────

def show_usuarios(gestor):
    st.header("👥 Usuarios Registrados")
    tab1, tab2 = st.tabs(["📋 Lista", "➕ Nuevo Usuario"])

    with tab1:
        usuarios = gestor.listar_usuarios()
        if usuarios:
            rows = []
            for u in usuarios:
                puntaje = gestor.obtener_o_crear_puntaje(u.id, TEMPORADA)
                rows.append({
                    "ID": u.id,
                    "Nombre Completo": u.nombre_completo,
                    "Saldo (pts)": puntaje.puntos_totales,
                    "Fecha Registro": u.fecha_registro.strftime("%d/%m/%Y %H:%M")
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("📋 No hay usuarios.")

    with tab2:
        st.subheader("Agregar Nuevo Usuario")
        with st.form("nuevo_usuario"):
            nombre    = st.text_input("Nombre",    placeholder="Juan")
            apellidos = st.text_input("Apellidos", placeholder="Pérez García")
            if st.form_submit_button("✅ Crear Usuario", use_container_width=True):
                if nombre and apellidos:
                    try:
                        u = gestor.insertar_usuario(nombre, apellidos)
                        # crear puntaje inicial automáticamente
                        gestor.obtener_o_crear_puntaje(u.id, TEMPORADA)
                        st.success(f"✅ Usuario creado: {u.nombre_completo} — Saldo inicial: {PUNTOS_INICIALES} pts")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
                else:
                    st.warning("⚠️ Completa todos los campos.")


# ── jornadas ───────────────────────────────────────────────────────────────

def show_jornadas(gestor):
    st.header("📅 Gestión de Jornadas")
    tab1, tab2, tab3 = st.tabs(["📋 Lista", "➕ Nueva", "🎮 Ver Partidos"])

    with tab1:
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if jornadas:
            rows = [{"ID": j.id, "Jornada": f"#{j.numero}", "Temporada": j.temporada,
                     "Partidos": j.total_partidos,
                     "Estado": "✅ Cerrada" if j.cerrada else "🔓 Abierta"} for j in jornadas]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("📋 No hay jornadas.")

    with tab2:
        with st.form("nueva_jornada"):
            numero = st.number_input("Número de Jornada", min_value=1, max_value=38, value=1)
            if st.form_submit_button("✅ Crear Jornada", use_container_width=True):
                if gestor.obtener_jornada(numero, TEMPORADA):
                    st.warning(f"⚠️ Jornada {numero} ya existe.")
                else:
                    gestor.crear_jornada(numero, TEMPORADA)
                    st.success(f"✅ Jornada {numero} creada."); st.rerun()

    with tab3:
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if jornadas:
            jsel = st.selectbox("Jornada:", jornadas, format_func=lambda j: f"Jornada {j.numero} ({j.total_partidos} partidos)")
            partidos = gestor.obtener_partidos_jornada(jsel.id)
            if partidos:
                rows = [{"ID": p.id, "Local": p.equipo_local.nombre, "Marcador": p.marcador,
                         "Visitante": p.equipo_visitante.nombre, "Estado": p.estado,
                         "Fecha": p.fecha_hora.strftime("%d/%m/%Y %H:%M")} for p in partidos]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("📋 No hay partidos en esta jornada.")
        else:
            st.warning("⚠️ No hay jornadas.")


# ── apuestas ───────────────────────────────────────────────────────────────

def show_apuestas(gestor):
    st.header("🎯 Hacer Apuestas")

    usuarios = gestor.listar_usuarios()
    jornadas = gestor.listar_jornadas(TEMPORADA)
    if not usuarios:
        st.warning("⚠️ No hay usuarios."); return
    if not jornadas:
        st.warning("⚠️ No hay jornadas."); return

    # ── selector usuario / jornada ─────────────────────────────
    col1, col2 = st.columns([1, 2])
    with col1:
        usuario = st.selectbox("👤 Usuario:", usuarios, format_func=lambda u: u.nombre_completo)
    with col2:
        jornada = st.selectbox("📅 Jornada:", jornadas,
                               format_func=lambda j: f"Jornada {j.numero} ({j.total_partidos} partidos)")

    # ── saldo del usuario ──────────────────────────────────────
    puntaje    = gestor.obtener_o_crear_puntaje(usuario.id, TEMPORADA)
    disponible = gestor.saldo_disponible(usuario.id, TEMPORADA)

    col_saldo1, col_saldo2 = st.columns(2)
    with col_saldo1:
        st.markdown(f"""
        <div class="saldo-box">
            <h3>💰 Saldo Total</h3>
            <h1>{puntaje.puntos_totales} pts</h1>
        </div>""", unsafe_allow_html=True)
    with col_saldo2:
        st.markdown(f"""
        <div class="saldo-box" style="background: linear-gradient(135deg, #ff9800, #f44336);">
            <h3>📊 Disponible para apostar</h3>
            <h1>{disponible} pts</h1>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── paso 1: seleccionar tipo de predicción ─────────────────
    st.subheader("Paso 1 — Selecciona tu tipo de predicción")

    tipos_keys = list(REGLAS.keys())
    tipos_cols = st.columns(3)
    tipo_seleccionado = None

    # usar session_state para mantener selección visual
    if 'tipo_sel' not in st.session_state:
        st.session_state['tipo_sel'] = tipos_keys[0]

    for i, tkey in enumerate(tipos_keys):
        info = REGLAS[tkey]
        activo = (st.session_state['tipo_sel'] == tkey)
        cls    = "tipo-card activo" if activo else "tipo-card"

        with tipos_cols[i]:
            st.markdown(f"""
            <div class="{cls}">
                <h4 style="margin:0 0 6px;">{info['label']}</h4>
                <p style="margin:0; font-size:0.82em; color:#555;">{info['desc']}</p>
            </div>""", unsafe_allow_html=True)
            if st.button(f"Seleccionar", key=f"btn_tipo_{tkey}",
                         use_container_width=True,
                         type="primary" if activo else "secondary"):
                st.session_state['tipo_sel'] = tkey
                st.rerun()

    tipo_seleccionado = st.session_state['tipo_sel']

    st.markdown("---")

    # ── paso 2: seleccionar partido ────────────────────────────
    st.subheader("Paso 2 — Selecciona el partido")
    partidos = gestor.obtener_partidos_jornada(jornada.id)
    if not partidos:
        st.info("📋 No hay partidos en esta jornada."); return

    partido = st.selectbox(
        "Partido:",
        partidos,
        format_func=lambda p: f"{p.equipo_local.nombre} vs {p.equipo_visitante.nombre}  —  {p.fecha_hora.strftime('%d/%m/%Y %H:%M')}"
    )

    # info del partido
    st.markdown(f"""
    <div style="background:#f0f2f6; padding:16px; border-radius:10px; border-left:5px solid #1f77b4;">
        <p style="margin:4px 0; font-size:1.1em;">
            <strong>{partido.equipo_local.nombre}</strong>
            <span style="color:#666;"> vs </span>
            <strong>{partido.equipo_visitante.nombre}</strong>
        </p>
        <p style="margin:2px 0; color:#666;">📅 {partido.fecha_hora.strftime("%A, %d de %B de %Y a las %H:%M")}</p>
        <p style="margin:2px 0; color:#666;">🏟️ {partido.equipo_local.estadio or 'Estadio por confirmar'}</p>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── paso 3: predicción según tipo ──────────────────────────
    st.subheader("Paso 3 — Haz tu predicción")

    prediccion = None   # se asigna abajo según tipo

    if tipo_seleccionado == "resultado":
        prediccion = _render_resultado(partido)

    elif tipo_seleccionado == "marcador":
        prediccion = _render_marcador(partido)

    elif tipo_seleccionado == "goles_total":
        prediccion = _render_goles_total(partido)

    st.markdown("---")

    # ── paso 4: puntos a apostar ───────────────────────────────
    st.subheader("Paso 4 — ¿Cuántos puntos quieres apostar?")

    opciones_filtradas = [o for o in OPCIONES_APUESTA if o <= disponible]
    if not opciones_filtradas:
        st.error("❌ No tienes puntos suficientes para apostar.")
        _render_mis_apuestas(gestor, usuario, jornada)
        return

    puntos_apostados = st.pills(
        "Selecciona:",
        options=opciones_filtradas,
        format_func=lambda x: f"{x} pts",
        selection_mode="single",
        default=opciones_filtradas[0]
    )

    # mostrar regla aplicada
    regla = REGLAS[tipo_seleccionado]
    if 'mult' in regla:
        ganancia_max = puntos_apostados * regla['mult']
        desc_regla   = f"Si aciertas ganas {puntos_apostados} × {regla['mult']} = **{ganancia_max} pts**  |  Si fallas pierdes **{puntos_apostados} pts**"
    else:
        ganancia_max = puntos_apostados + regla['bonus']
        desc_regla   = f"Si aciertas ganas {puntos_apostados} + {regla['bonus']} = **{ganancia_max} pts**  |  Si fallas pierdes **{puntos_apostados} pts**"
    st.info(f"💡 {desc_regla}")

    st.markdown("---")

    # ── confirmar apuesta ──────────────────────────────────────
    if prediccion and puntos_apostados:
        # resumen visual
        pred_texto = _texto_prediccion(tipo_seleccionado, prediccion, partido)
        st.markdown(f"""
        <div style="background:#e8f5e9; border:2px solid #4caf50; border-radius:10px; padding:16px;">
            <p style="margin:4px 0;"><strong>Tipo:</strong> {regla['label']}</p>
            <p style="margin:4px 0;"><strong>Partido:</strong> {partido.equipo_local.nombre} vs {partido.equipo_visitante.nombre}</p>
            <p style="margin:4px 0;"><strong>Tu predicción:</strong> {pred_texto}</p>
            <p style="margin:4px 0;"><strong>Puntos apostados:</strong> {puntos_apostados} pts</p>
        </div>""", unsafe_allow_html=True)

        col_btn = st.columns([1,2,1])
        with col_btn[1]:
            if st.button("✅ Confirmar Apuesta", type="primary", use_container_width=True):
                try:
                    gestor.hacer_apuesta(usuario.id, partido.id, tipo_seleccionado, prediccion, puntos_apostados)
                    st.success("🎉 ¡Apuesta guardada!")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                except ValueError as e:
                    st.error(f"❌ {e}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

    st.markdown("---")
    _render_mis_apuestas(gestor, usuario, jornada)


# ── helpers de predicción por tipo ─────────────────────────────────────────

def _render_resultado(partido) -> Optional[str]:
    """Tres tarjetas + botones. Retorna '1' | 'X' | '2' | None."""

    # key que NO es propiedad de ningún widget → podemos escribirlo libre
    KEY = '_resultado_sel'
    if KEY not in st.session_state:
        st.session_state[KEY] = None

    opciones = [
        ('1', '🏆 Gana Local',      partido.equipo_local.nombre,      '#f0fff0', '#4caf50', '#2e7d32'),
        ('X', '🤝 Empate',          'Ninguno gana',                   '#fffde7', '#fdd835', '#f9a825'),
        ('2', '🏆 Gana Visitante',  partido.equipo_visitante.nombre,  '#e3f2fd', '#42a5f5', '#1565c0'),
    ]

    cols = st.columns(3)
    for val, titulo, subtitulo, bg, borde, color in opciones:
        activo = (st.session_state[KEY] == val)
        with cols[opciones.index((val, titulo, subtitulo, bg, borde, color))]:
            st.markdown(f"""
            <div style="text-align:center; padding:14px; border-radius:12px;
                 background:{'#e8f5e9' if activo else bg};
                 border:{'3px' if activo else '2px'} solid {borde};
                 box-shadow:{'0 2px 8px rgba(0,0,0,0.15)' if activo else 'none'};">
                <h4 style="margin:0 0 4px; color:{color};">{titulo}</h4>
                <p style="margin:0; font-size:0.88em; color:#555;">{subtitulo}</p>
            </div>""", unsafe_allow_html=True)
            if st.button(
                "✓ Seleccionado" if activo else "Seleccionar",
                key=f"btn_res_{val}",
                use_container_width=True,
                type="primary" if activo else "secondary"
            ):
                st.session_state[KEY] = val
                st.rerun()

    sel = st.session_state[KEY]
    if not sel:
        st.warning("⚠️ Selecciona una opción.")
    return sel


def _render_marcador(partido) -> Optional[str]:
    """Dos number_inputs para marcador exacto. Retorna 'GL-GV'."""
    col1, col2 = st.columns(2)
    with col1:
        gl = st.number_input(f"⚽ Goles {partido.equipo_local.nombre}", min_value=0, max_value=10, value=0, key="marc_local")
    with col2:
        gv = st.number_input(f"⚽ Goles {partido.equipo_visitante.nombre}", min_value=0, max_value=10, value=0, key="marc_visitante")
    return f"{gl}-{gv}"


def _render_goles_total(partido) -> Optional[str]:
    """Botones Bajo / Alto."""
    st.write("¿Cuántos goles habrá en total en el partido?")

    if 'goles_total_sel' not in st.session_state:
        st.session_state['goles_total_sel'] = None

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div style="text-align:center; padding:14px; background:#fff3e0; border-radius:12px; border:2px solid #ff9800;">
            <h4 style="margin:0; color:#e65100;">⬇️ Bajo (2 o menos goles)</h4>
        </div>""", unsafe_allow_html=True)
        if st.button("Seleccionar Bajo", use_container_width=True,
                     type="primary" if st.session_state['goles_total_sel'] == 'bajo' else "secondary",
                     key="btn_bajo"):
            st.session_state['goles_total_sel'] = 'bajo'
            st.rerun()

    with col2:
        st.markdown("""
        <div style="text-align:center; padding:14px; background:#e8eaf6; border-radius:12px; border:2px solid #5c6bc0;">
            <h4 style="margin:0; color:#283593;">⬆️ Alto (3 o más goles)</h4>
        </div>""", unsafe_allow_html=True)
        if st.button("Seleccionar Alto", use_container_width=True,
                     type="primary" if st.session_state['goles_total_sel'] == 'alto' else "secondary",
                     key="btn_alto"):
            st.session_state['goles_total_sel'] = 'alto'
            st.rerun()

    sel = st.session_state.get('goles_total_sel')
    if not sel:
        st.warning("⚠️ Selecciona Bajo u Alto.")
    return sel


def _texto_prediccion(tipo, prediccion, partido) -> str:
    if tipo == 'resultado':
        return {"1": f"Gana {partido.equipo_local.nombre}",
                "X": "Empate",
                "2": f"Gana {partido.equipo_visitante.nombre}"}[prediccion]
    if tipo == 'marcador':
        parts = prediccion.split('-')
        return f"{partido.equipo_local.nombre} {parts[0]} - {parts[1]} {partido.equipo_visitante.nombre}"
    if tipo == 'goles_total':
        return "⬇️ Bajo (≤ 2 goles)" if prediccion == 'bajo' else "⬆️ Alto (≥ 3 goles)"
    return prediccion


# ── tabla "mis apuestas" ───────────────────────────────────────────────────

def _render_mis_apuestas(gestor, usuario, jornada):
    st.subheader("📋 Mis apuestas en esta jornada")

    apuestas = gestor.session.query(Apuesta).join(Partido).filter(
        Apuesta.usuario_id == usuario.id,
        Partido.jornada_id == jornada.id
    ).all()

    if not apuestas:
        st.info("📋 Aún no has hecho apuestas en esta jornada.")
        return

    rows = []
    for ap in apuestas:
        p = ap.partido
        pred_texto = _texto_prediccion(ap.tipo_apuesta, ap.prediccion, p)
        regla      = REGLAS[ap.tipo_apuesta]

        if p.estado == 'finalizado' and ap.puntos_obtenidos is not None:
            if ap.acerto:
                estado = "✅ Acertaste"
                puntos = f"+{ap.puntos_obtenidos - ap.puntos_apostados} pts"
            else:
                estado = "❌ Fallaste"
                puntos = f"-{ap.puntos_apostados} pts"
            resultado = p.marcador
        else:
            estado    = "⏳ Pendiente"
            puntos    = "—"
            resultado = "vs"

        rows.append({
            "Partido":      f"{p.equipo_local.nombre} vs {p.equipo_visitante.nombre}",
            "Fecha":        p.fecha_hora.strftime("%d/%m %H:%M"),
            "Tipo":         regla['label'],
            "Tu predicción": pred_texto,
            "Resultado":    resultado,
            "Apostado":     f"{ap.puntos_apostados} pts",
            "Estado":       estado,
            "Ganancia":     puntos,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # resumen métrico
    total   = len(apuestas)
    aciertos= sum(1 for a in apuestas if a.acerto == True)
    perdidos= sum(a.puntos_apostados for a in apuestas if a.acerto == False)
    ganados = sum((a.puntos_obtenidos or 0) - a.puntos_apostados for a in apuestas if a.acerto == True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Apuestas", total)
    c2.metric("Aciertos",       aciertos)
    c3.metric("Ganancia neta",  f"+{ganados} pts")
    c4.metric("Pérdidas",       f"-{perdidos} pts")


# ── clasificación ──────────────────────────────────────────────────────────

def show_clasificacion(gestor):
    st.header("📊 Clasificación General")
    clasificacion = gestor.obtener_clasificacion(TEMPORADA)
    if not clasificacion:
        st.info("📋 No hay datos de clasificación aún."); return

    # podio
    st.subheader("🏆 Podio")
    medallas = ["🥇", "🥈", "🥉"]
    cols = st.columns(3)
    for i, p in enumerate(clasificacion[:3]):
        with cols[i]:
            st.markdown(f"""
            <div class="metric-card" style="text-align:center;">
                <h1>{medallas[i]}</h1>
                <h3>{p.usuario.nombre_completo}</h3>
                <h2>{p.puntos_totales} pts</h2>
                <p>Aciertos: {p.aciertos} | Fallos: {p.fallos}</p>
                <p>Precisión: {p.porcentaje_aciertos:.1f}%</p>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📋 Clasificación Completa")

    rows = []
    for pos, p in enumerate(clasificacion, 1):
        rows.append({
            "Pos": pos,
            "Usuario": p.usuario.nombre_completo,
            "Saldo (pts)": p.puntos_totales,
            "Aciertos": p.aciertos,
            "Fallos": p.fallos,
            "Apuestas": p.partidos_apostados,
            "% Acierto": f"{p.porcentaje_aciertos:.1f}%"
        })

    df = pd.DataFrame(rows)

    def highlight_top3(row):
        return ['background-color: #fff3cd'] * len(row) if row['Pos'] <= 3 else [''] * len(row)

    st.dataframe(df.style.apply(highlight_top3, axis=1), use_container_width=True, hide_index=True)


# ── administración ─────────────────────────────────────────────────────────

def show_admin(gestor):
    st.header("⚙️ Administración del Sistema")
    tab1, tab2, tab3 = st.tabs(["🔄 Cargar desde API", "🎮 Actualizar Resultados", "📊 Procesar Jornada"])

    with tab1:
        st.subheader("Cargar Datos desde API")
        st.markdown("### 1️⃣ Cargar Equipos")
        st.warning("⚠️ Esto eliminará todos los equipos y partidos existentes.")
        if st.button("🔄 Cargar Equipos desde API", type="primary"):
            with st.spinner("Cargando equipos…"):
                try:
                    n = gestor.cargar_equipos_desde_api()
                    st.success(f"✅ {n} equipos cargados.")
                except Exception as e:
                    st.error(f"❌ {e}")

        st.markdown("---")
        st.markdown("### 2️⃣ Cargar Partidos")
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.info("📋 Crea una jornada primero.")
        else:
            jsel = st.selectbox("Jornada:", jornadas, format_func=lambda j: f"Jornada {j.numero}")
            if st.button("🔄 Cargar Partidos desde API", type="primary"):
                st.warning("⏳ Puede tardar varios minutos…")
                try:
                    n = gestor.cargar_partidos_desde_api(jsel.id)
                    st.success(f"✅ {n} partidos cargados.")
                except Exception as e:
                    st.error(f"❌ {e}")

    with tab2:
        st.subheader("Actualizar Resultados")
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.warning("⚠️ No hay jornadas.")
        else:
            jsel = st.selectbox("Jornada:", jornadas, format_func=lambda j: f"Jornada {j.numero}", key="j_res")
            partidos = gestor.obtener_partidos_jornada(jsel.id)
            if partidos:
                partido = st.selectbox("Partido:", partidos,
                    format_func=lambda p: f"{p.equipo_local.nombre} vs {p.equipo_visitante.nombre} — {p.fecha_hora.strftime('%d/%m %H:%M')} ({p.estado})")

                st.markdown(f"""
                <div class="metric-card">
                    <h4>⚽ {partido.equipo_local.nombre} vs {partido.equipo_visitante.nombre}</h4>
                    <p>📅 {partido.fecha_hora.strftime("%d/%m/%Y a las %H:%M")} | 🏟️ {partido.equipo_local.estadio or 'Por confirmar'}</p>
                    <p>Estado: <strong>{partido.estado}</strong></p>
                </div>""", unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    gl = st.number_input(f"⚽ Goles {partido.equipo_local.nombre}", min_value=0, max_value=20,
                                         value=partido.goles_local if partido.goles_local is not None else 0)
                with col2:
                    gv = st.number_input(f"⚽ Goles {partido.equipo_visitante.nombre}", min_value=0, max_value=20,
                                         value=partido.goles_visitante if partido.goles_visitante is not None else 0)

                if st.button("✅ Actualizar Resultado", type="primary", use_container_width=True):
                    try:
                        gestor.actualizar_resultado(partido.id, gl, gv)
                        st.success(f"✅ {partido.equipo_local.nombre} {gl}-{gv} {partido.equipo_visitante.nombre}")
                        time.sleep(1); st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
            else:
                st.info("📋 No hay partidos.")

    with tab3:
        st.subheader("Procesar Jornada Finalizada")
        st.info("💡 Calcula puntos de todas las apuestas de la jornada y actualiza saldos.")
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.warning("⚠️ No hay jornadas.")
        else:
            jsel = st.selectbox("Jornada:", jornadas, format_func=lambda j: f"Jornada {j.numero}", key="j_proc")
            if st.button("🎯 Procesar Jornada", type="primary"):
                with st.spinner("Procesando…"):
                    try:
                        res = gestor.procesar_jornada(jsel.id, TEMPORADA)
                        st.success(f"""
                        ✅ Jornada procesada:
                        - Apuestas procesadas: {res['apuestas_procesadas']}
                        - Puntos ganados: +{res['puntos_otorgados']}
                        - Puntos perdidos: -{res['puntos_perdidos']}
                        """)
                    except Exception as e:
                        st.error(f"❌ {e}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()