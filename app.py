"""
LA POLLA - LIGA ESPAÑOLA (Streamlit + Supabase)
================================================
Sistema de quinielas con base de datos en Supabase (PostgreSQL).

CONFIGURACIÓN REQUERIDA (en .streamlit/secrets.toml):
    [supabase]
    url = "https://xxxx.supabase.co"
    key = "tu_anon_key_aqui"
"""

import streamlit as st
from supabase import create_client, Client
from datetime import datetime
from typing import Optional, List, Dict
import requests
import time
import pandas as pd

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

REGLAS = {
    "resultado":   {"label": "Resultado",          "mult": 2,  "desc": "Predice si gana local, empate o visitante.  Acierto → apuestado × 2"},
    "marcador":    {"label": "Marcador Exacto",    "mult": 3,  "desc": "Adivina el marcador exacto (ej. 2-1).  Acierto → apuestado × 3"},
    "goles_total": {"label": "Total de Goles",     "bonus": 5, "desc": "¿Habrá 2 o menos goles (Bajo) o 3 o más (Alto)?  Acierto → apuestado + 5"},
}

EQUIPOS_DEMO = [
    {"id": 81,  "nombre": "FC Barcelona",               "nombre_corto": "BAR", "estadio": "Spotify Camp Nou"},
    {"id": 86,  "nombre": "Real Madrid CF",              "nombre_corto": "RMA", "estadio": "Santiago Bernabéu"},
    {"id": 78,  "nombre": "Club Atlético de Madrid",     "nombre_corto": "ATM", "estadio": "Cívitas Metropolitano"},
    {"id": 92,  "nombre": "Real Sociedad de Fútbol",     "nombre_corto": "RSO", "estadio": "Reale Arena"},
    {"id": 94,  "nombre": "Villarreal CF",               "nombre_corto": "VIL", "estadio": "Estadio de la Cerámica"},
    {"id": 77,  "nombre": "Athletic Club",               "nombre_corto": "ATH", "estadio": "San Mamés"},
    {"id": 90,  "nombre": "Real Betis Balompié",         "nombre_corto": "BET", "estadio": "Benito Villamarín"},
    {"id": 558, "nombre": "RC Celta de Vigo",            "nombre_corto": "CEL", "estadio": "Abanca-Balaídos"},
    {"id": 89,  "nombre": "RCD Mallorca",                "nombre_corto": "MLL", "estadio": "Visit Mallorca Estadi"},
    {"id": 82,  "nombre": "Getafe CF",                   "nombre_corto": "GET", "estadio": "Coliseum Alfonso Pérez"},
    {"id": 79,  "nombre": "CA Osasuna",                  "nombre_corto": "OSA", "estadio": "El Sadar"},
    {"id": 87,  "nombre": "Rayo Vallecano de Madrid",    "nombre_corto": "RAY", "estadio": "Campo de Fútbol de Vallecas"},
    {"id": 95,  "nombre": "Valencia CF",                 "nombre_corto": "VAL", "estadio": "Mestalla"},
    {"id": 559, "nombre": "Sevilla FC",                  "nombre_corto": "SEV", "estadio": "Ramón Sánchez-Pizjuán"},
    {"id": 263, "nombre": "Deportivo Alavés",            "nombre_corto": "ALA", "estadio": "Mendizorroza"},
    {"id": 275, "nombre": "UD Las Palmas",               "nombre_corto": "LPA", "estadio": "Estadio de Gran Canaria"},
    {"id": 264, "nombre": "RCD Espanyol de Barcelona",  "nombre_corto": "ESP", "estadio": "RCDE Stadium"},
    {"id": 298, "nombre": "Girona FC",                  "nombre_corto": "GIR", "estadio": "Montilivi"},
    {"id": 285, "nombre": "CD Leganés",                 "nombre_corto": "LEG", "estadio": "Butarque"},
    {"id": 250, "nombre": "Real Valladolid CF",         "nombre_corto": "VLL", "estadio": "José Zorrilla"},
]


# =============================================================================
# CLIENTE SUPABASE
# =============================================================================

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


# =============================================================================
# GESTOR DE LA LIGA
# =============================================================================

class GestorLiga:

    def __init__(self):
        self.sb: Client = get_supabase()

    # ── Utilidades de lógica de partido ───────────────────────

    def _resultado_partido(self, p: Dict) -> str:
        if p.get("goles_local") is None or p.get("goles_visitante") is None:
            return "-"
        if p["goles_local"] > p["goles_visitante"]:  return "1"
        if p["goles_local"] < p["goles_visitante"]:  return "2"
        return "X"

    def _marcador_partido(self, p: Dict) -> str:
        if p.get("goles_local") is None:
            return "vs"
        return f"{p['goles_local']}-{p['goles_visitante']}"

    def _goles_totales(self, p: Dict) -> Optional[int]:
        if p.get("goles_local") is None:
            return None
        return p["goles_local"] + p["goles_visitante"]

    def _acerto_apuesta(self, ap: Dict, partido: Dict) -> Optional[bool]:
        if partido.get("estado") != "finalizado":
            return None
        tipo = ap["tipo_apuesta"]
        pred = ap["prediccion"]
        if tipo == "resultado":
            return pred == self._resultado_partido(partido)
        if tipo == "marcador":
            return pred == f"{partido['goles_local']}-{partido['goles_visitante']}"
        if tipo == "goles_total":
            total = self._goles_totales(partido)
            if total is None:
                return None
            return total <= 2 if pred == "bajo" else total >= 3
        return None

    def _calcular_puntos_netos(self, ap: Dict, partido: Dict) -> int:
        acerto = self._acerto_apuesta(ap, partido)
        if acerto is None:
            return 0
        if not acerto:
            return -ap["puntos_apostados"]
        regla = REGLAS[ap["tipo_apuesta"]]
        if "mult" in regla:
            ganancia = ap["puntos_apostados"] * regla["mult"]
        else:
            ganancia = ap["puntos_apostados"] + regla["bonus"]
        return ganancia - ap["puntos_apostados"]

    def _puntos_obtenidos(self, ap: Dict, partido: Dict) -> int:
        acerto = self._acerto_apuesta(ap, partido)
        if acerto is None or not acerto:
            return 0
        regla = REGLAS[ap["tipo_apuesta"]]
        if "mult" in regla:
            return ap["puntos_apostados"] * regla["mult"]
        return ap["puntos_apostados"] + regla["bonus"]

    # ── Equipos ────────────────────────────────────────────────

    def listar_equipos(self) -> List[Dict]:
        resp = self.sb.table("equipos").select("*").order("nombre").execute()
        return resp.data or []

    def cargar_equipos_desde_api(self) -> int:
        """Carga equipos reales desde football-data.org."""
        url = f"{API_CONFIG['base_url']}/competitions/{API_CONFIG['competition']}/teams"
        try:
            r = requests.get(url, headers={"X-Auth-Token": API_CONFIG["key"]}, timeout=15)
            r.raise_for_status()
            equipos_api = r.json().get("teams", [])
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Error API: {e}")

        self.sb.table("equipos").delete().neq("id", 0).execute()
        for eq in equipos_api:
            self.sb.table("equipos").upsert({
                "id":           eq["id"],
                "nombre":       eq["name"],
                "nombre_corto": eq.get("tla", eq.get("shortName", "???"))[:5],
                "estadio":      eq.get("venue", "")
            }).execute()
        return len(equipos_api)

    def cargar_equipos_demo(self) -> int:
        """Carga equipos locales (sin API)."""
        self.sb.table("equipos").delete().neq("id", 0).execute()
        self.sb.table("equipos").insert(EQUIPOS_DEMO).execute()
        return len(EQUIPOS_DEMO)

    # ── Usuarios ───────────────────────────────────────────────

    def listar_usuarios(self) -> List[Dict]:
        resp = self.sb.table("usuarios").select("*").eq("activo", True).order("nombre").execute()
        return resp.data or []

    def insertar_usuario(self, nombre: str, apellidos: str) -> Dict:
        resp = self.sb.table("usuarios").insert({
            "nombre":         nombre,
            "apellidos":      apellidos,
            "fecha_registro": datetime.now().isoformat(),
            "activo":         True
        }).execute()
        return resp.data[0]

    def nombre_completo(self, u: Dict) -> str:
        return f"{u['nombre']} {u['apellidos']}"

    # ── Jornadas ───────────────────────────────────────────────

    def listar_jornadas(self, temporada: str) -> List[Dict]:
        resp = (self.sb.table("jornadas")
                .select("*")
                .eq("temporada", temporada)
                .order("numero")
                .execute())
        return resp.data or []

    def obtener_jornada(self, numero: int, temporada: str) -> Optional[Dict]:
        resp = (self.sb.table("jornadas")
                .select("*")
                .eq("numero", numero)
                .eq("temporada", temporada)
                .execute())
        return resp.data[0] if resp.data else None

    def crear_jornada(self, numero: int, temporada: str) -> Dict:
        resp = self.sb.table("jornadas").insert({
            "numero": numero, "temporada": temporada, "cerrada": False
        }).execute()
        return resp.data[0]

    def total_partidos_jornada(self, jornada_id: int) -> int:
        resp = (self.sb.table("partidos")
                .select("id", count="exact")
                .eq("jornada_id", jornada_id)
                .execute())
        return resp.count or 0

    # ── Partidos ───────────────────────────────────────────────

    def obtener_partidos_jornada(self, jornada_id: int) -> List[Dict]:
        resp = (self.sb.table("partidos")
                .select("*, equipo_local:equipos!equipo_local_id(*), equipo_visitante:equipos!equipo_visitante_id(*)")
                .eq("jornada_id", jornada_id)
                .order("fecha_hora")
                .execute())
        return resp.data or []

    def crear_partido(self, jornada_id: int, equipo_local_id: int,
                      equipo_visitante_id: int, fecha_hora: str) -> Dict:
        resp = self.sb.table("partidos").insert({
            "jornada_id":          jornada_id,
            "equipo_local_id":     equipo_local_id,
            "equipo_visitante_id": equipo_visitante_id,
            "fecha_hora":          fecha_hora,
            "estado":              "programado"
        }).execute()
        return resp.data[0]

    def cargar_partidos_desde_api(self, jornada_id: int) -> int:
        """
        Recorre todos los equipos cargados y recopila partidos SCHEDULED de La Liga.
        Idéntica lógica al original, adaptada a Supabase.
        """
        equipos = self.listar_equipos()
        if not equipos:
            raise RuntimeError("No hay equipos cargados. Carga equipos primero.")

        unicos: dict = {}
        prog   = st.progress(0)
        status = st.empty()
        total  = len(equipos)

        for i, eq in enumerate(equipos):
            status.text(f"🔄 Consultando {eq['nombre_corto']}… ({i+1}/{total})")
            prog.progress((i + 1) / total)

            url = f"{API_CONFIG['base_url']}/teams/{eq['id']}/matches?status=SCHEDULED"
            try:
                r = requests.get(url, headers={"X-Auth-Token": API_CONFIG["key"]}, timeout=15)
                r.raise_for_status()
                for p in r.json().get("matches", []):
                    if p.get("competition", {}).get("code") != API_CONFIG["competition"]:
                        continue
                    pid = p["id"]
                    if pid not in unicos:
                        unicos[pid] = {
                            "id":           pid,
                            "jornada_id":   jornada_id,
                            "local_id":     p["homeTeam"]["id"],
                            "visitante_id": p["awayTeam"]["id"],
                            "fecha_hora":   p["utcDate"].replace("Z", "+00:00"),
                        }
            except Exception as e:
                st.warning(f"⚠️ {eq['nombre_corto']}: {e}")

            time.sleep(6)   # respetar límite de la API (10 req/min plan gratuito)

        prog.empty()
        status.empty()

        # Obtener IDs ya existentes en esa jornada para no duplicar
        resp_existentes = (self.sb.table("partidos")
                           .select("id")
                           .eq("jornada_id", jornada_id)
                           .execute())
        ids_existentes = {r["id"] for r in (resp_existentes.data or [])}

        insertados = 0
        for d in unicos.values():
            if d["id"] in ids_existentes:
                continue
            # Verificar que ambos equipos existan en nuestra BD
            resp_loc = self.sb.table("equipos").select("id").eq("id", d["local_id"]).execute()
            resp_vis = self.sb.table("equipos").select("id").eq("id", d["visitante_id"]).execute()
            if not resp_loc.data or not resp_vis.data:
                continue
            self.sb.table("partidos").insert({
                "id":                  d["id"],
                "jornada_id":          d["jornada_id"],
                "equipo_local_id":     d["local_id"],
                "equipo_visitante_id": d["visitante_id"],
                "fecha_hora":          d["fecha_hora"],
                "estado":              "programado",
            }).execute()
            insertados += 1

        return insertados

    def actualizar_resultado(self, partido_id: int, gl: int, gv: int):
        self.sb.table("partidos").update({
            "goles_local":     gl,
            "goles_visitante": gv,
            "estado":          "finalizado"
        }).eq("id", partido_id).execute()

    # ── Puntaje / Saldo ────────────────────────────────────────

    def obtener_o_crear_puntaje(self, usuario_id: int, temporada: str) -> Dict:
        resp = (self.sb.table("puntajes")
                .select("*")
                .eq("usuario_id", usuario_id)
                .eq("temporada", temporada)
                .execute())
        if resp.data:
            return resp.data[0]
        resp2 = self.sb.table("puntajes").insert({
            "usuario_id":         usuario_id,
            "temporada":          temporada,
            "puntos_totales":     PUNTOS_INICIALES,
            "aciertos":           0,
            "fallos":             0,
            "partidos_apostados": 0
        }).execute()
        return resp2.data[0]

    def puntos_comprometidos(self, usuario_id: int, temporada: str) -> int:
        """Suma puntos_apostados de apuestas en partidos NO finalizados."""
        resp = (self.sb.table("apuestas")
                .select("puntos_apostados, partidos!inner(estado)")
                .eq("usuario_id", usuario_id)
                .is_("puntos_obtenidos", "null")
                .execute())
        if not resp.data:
            return 0
        return sum(
            a["puntos_apostados"]
            for a in resp.data
            if a.get("partidos", {}).get("estado") != "finalizado"
        )

    def saldo_disponible(self, usuario_id: int, temporada: str) -> int:
        puntaje       = self.obtener_o_crear_puntaje(usuario_id, temporada)
        comprometidos = self.puntos_comprometidos(usuario_id, temporada)
        return puntaje["puntos_totales"] - comprometidos

    # ── Apuestas ───────────────────────────────────────────────

    def hacer_apuesta(self, usuario_id: int, partido_id: int,
                      tipo: str, prediccion: str, puntos_apostados: int) -> Dict:
        disponible = self.saldo_disponible(usuario_id, TEMPORADA)
        if puntos_apostados > disponible:
            raise ValueError(f"Saldo insuficiente. Disponible: {disponible} pts")

        resp = (self.sb.table("apuestas")
                .select("id")
                .eq("usuario_id",   usuario_id)
                .eq("partido_id",   partido_id)
                .eq("tipo_apuesta", tipo)
                .execute())
        data = {
            "usuario_id":       usuario_id,
            "partido_id":       partido_id,
            "tipo_apuesta":     tipo,
            "prediccion":       prediccion,
            "puntos_apostados": puntos_apostados,
            "puntos_obtenidos": None,
            "fecha_apuesta":    datetime.now().isoformat()
        }
        if resp.data:
            r2 = self.sb.table("apuestas").update(data).eq("id", resp.data[0]["id"]).execute()
        else:
            r2 = self.sb.table("apuestas").insert(data).execute()
        return r2.data[0]

    def apuestas_usuario_jornada(self, usuario_id: int, jornada_id: int) -> List[Dict]:
        resp = (self.sb.table("apuestas")
                .select("*, partidos!inner(*, equipo_local:equipos!equipo_local_id(*), equipo_visitante:equipos!equipo_visitante_id(*))")
                .eq("usuario_id", usuario_id)
                .eq("partidos.jornada_id", jornada_id)
                .execute())
        return resp.data or []

    def apuesta_existente(self, usuario_id: int, partido_id: int, tipo: str) -> Optional[Dict]:
        resp = (self.sb.table("apuestas")
                .select("*")
                .eq("usuario_id",   usuario_id)
                .eq("partido_id",   partido_id)
                .eq("tipo_apuesta", tipo)
                .execute())
        return resp.data[0] if resp.data else None

    # ── Clasificación ──────────────────────────────────────────

    def obtener_clasificacion(self, temporada: str) -> List[Dict]:
        resp = (self.sb.table("puntajes")
                .select("*, usuarios(*)")
                .eq("temporada", temporada)
                .order("puntos_totales", desc=True)
                .order("aciertos", desc=True)
                .execute())
        return resp.data or []

    # ── Procesar jornada ───────────────────────────────────────

    def procesar_jornada(self, jornada_id: int, temporada: str) -> dict:
        resumen = {"apuestas_procesadas": 0, "puntos_otorgados": 0, "puntos_perdidos": 0}

        resp = (self.sb.table("apuestas")
                .select("*, partidos!inner(*)")
                .eq("partidos.jornada_id", jornada_id)
                .eq("partidos.estado", "finalizado")
                .is_("puntos_obtenidos", "null")
                .execute())
        apuestas = resp.data or []

        for ap in apuestas:
            partido       = ap["partidos"]
            neta          = self._calcular_puntos_netos(ap, partido)
            pts_obtenidos = self._puntos_obtenidos(ap, partido)

            self.sb.table("apuestas").update({
                "puntos_obtenidos": pts_obtenidos
            }).eq("id", ap["id"]).execute()

            puntaje = self.obtener_o_crear_puntaje(ap["usuario_id"], temporada)
            acerto  = self._acerto_apuesta(ap, partido)
            update  = {
                "puntos_totales":     puntaje["puntos_totales"] + neta,
                "partidos_apostados": puntaje["partidos_apostados"] + 1,
            }
            if acerto:
                update["aciertos"] = puntaje["aciertos"] + 1
                resumen["puntos_otorgados"] += neta
            else:
                update["fallos"] = puntaje["fallos"] + 1
                resumen["puntos_perdidos"] += ap["puntos_apostados"]

            self.sb.table("puntajes").update(update).eq("id", puntaje["id"]).execute()
            resumen["apuestas_procesadas"] += 1

        return resumen


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
# HELPERS UI
# =============================================================================

def _porcentaje_aciertos(p: Dict) -> float:
    if p.get("partidos_apostados", 0) == 0:
        return 0.0
    return (p.get("aciertos", 0) / p["partidos_apostados"]) * 100


def _texto_prediccion(tipo: str, prediccion: str, partido: Dict) -> str:
    local  = partido.get("equipo_local",     {}).get("nombre", "Local")
    visita = partido.get("equipo_visitante", {}).get("nombre", "Visitante")
    if tipo == "resultado":
        return {"1": f"Gana {local}", "X": "Empate", "2": f"Gana {visita}"}.get(prediccion, prediccion)
    if tipo == "marcador":
        parts = prediccion.split("-")
        return f"{local} {parts[0]} - {parts[1]} {visita}"
    if tipo == "goles_total":
        return "⬇️ Bajo (≤ 2 goles)" if prediccion == "bajo" else "⬆️ Alto (≥ 3 goles)"
    return prediccion


# =============================================================================
# PÁGINAS
# =============================================================================

def show_dashboard(gestor: GestorLiga):
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
        c4.metric("🏆 Líder", gestor.nombre_completo(lider["usuarios"]),
                  f"{lider['puntos_totales']} pts")
    else:
        c4.metric("🏆 Líder", "Sin datos")

    st.markdown("---")
    if clasificacion:
        st.subheader("🏆 Top 5 Clasificación")
        rows = []
        for i, p in enumerate(clasificacion[:5], 1):
            rows.append({
                "Pos":         f"#{i}",
                "Usuario":     gestor.nombre_completo(p["usuarios"]),
                "Saldo (pts)": p["puntos_totales"],
                "Aciertos":    p["aciertos"],
                "Fallos":      p["fallos"],
                "% Acierto":   f"{_porcentaje_aciertos(p):.1f}%"
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("📋 No hay datos de clasificación aún.")

    st.markdown("---")
    st.subheader("📅 Jornadas Recientes")
    if jornadas:
        rows = []
        for j in jornadas[-5:]:
            rows.append({
                "Jornada":   f"#{j['numero']}",
                "Temporada": j["temporada"],
                "Partidos":  gestor.total_partidos_jornada(j["id"]),
                "Estado":    "✅ Cerrada" if j["cerrada"] else "🔓 Abierta"
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("📋 No hay jornadas registradas.")


def show_equipos(gestor: GestorLiga):
    st.header("⚽ Equipos de La Liga")
    equipos = gestor.listar_equipos()
    if not equipos:
        st.warning("⚠️ No hay equipos. Ve a Administración → Cargar Equipos.")
        return
    search = st.text_input("🔍 Buscar equipo", placeholder="Nombre…")
    if search:
        equipos = [e for e in equipos if search.lower() in e["nombre"].lower()]
    cols = st.columns(3)
    for i, e in enumerate(equipos):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="metric-card">
                <h3>{e['nombre']}</h3>
                <p><strong>Código:</strong> {e['nombre_corto']}</p>
                <p>🏟️ {e.get('estadio') or 'Sin estadio'}</p>
            </div><br>""", unsafe_allow_html=True)
    st.info(f"📊 Total: {len(equipos)} equipos")


def show_usuarios(gestor: GestorLiga):
    st.header("👥 Usuarios Registrados")
    tab1, tab2 = st.tabs(["📋 Lista", "➕ Nuevo Usuario"])

    with tab1:
        usuarios = gestor.listar_usuarios()
        if usuarios:
            rows = []
            for u in usuarios:
                puntaje = gestor.obtener_o_crear_puntaje(u["id"], TEMPORADA)
                rows.append({
                    "ID":              u["id"],
                    "Nombre Completo": gestor.nombre_completo(u),
                    "Saldo (pts)":     puntaje["puntos_totales"],
                    "Fecha Registro":  u.get("fecha_registro", "")[:10],
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
                        u = gestor.insertar_usuario(nombre.strip(), apellidos.strip())
                        gestor.obtener_o_crear_puntaje(u["id"], TEMPORADA)
                        st.success(f"✅ Usuario creado: {gestor.nombre_completo(u)} — Saldo inicial: {PUNTOS_INICIALES} pts")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
                else:
                    st.warning("⚠️ Completa todos los campos.")


def show_jornadas(gestor: GestorLiga):
    st.header("📅 Gestión de Jornadas")
    tab1, tab2, tab3 = st.tabs(["📋 Lista", "➕ Nueva", "🎮 Ver Partidos"])

    with tab1:
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if jornadas:
            rows = []
            for j in jornadas:
                rows.append({
                    "ID":        j["id"],
                    "Jornada":   f"#{j['numero']}",
                    "Temporada": j["temporada"],
                    "Partidos":  gestor.total_partidos_jornada(j["id"]),
                    "Estado":    "✅ Cerrada" if j["cerrada"] else "🔓 Abierta"
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("📋 No hay jornadas.")

    with tab2:
        with st.form("nueva_jornada"):
            numero = st.number_input("Número de Jornada", min_value=1, max_value=38, value=1)
            if st.form_submit_button("✅ Crear Jornada", use_container_width=True):
                if gestor.obtener_jornada(numero, TEMPORADA):
                    st.warning(f"⚠️ La jornada {numero} ya existe.")
                else:
                    gestor.crear_jornada(numero, TEMPORADA)
                    st.success(f"✅ Jornada {numero} creada.")
                    st.rerun()

    with tab3:
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.warning("⚠️ No hay jornadas."); return

        jsel     = st.selectbox("Jornada:", jornadas,
                                format_func=lambda j: f"Jornada {j['numero']} ({gestor.total_partidos_jornada(j['id'])} partidos)")
        partidos = gestor.obtener_partidos_jornada(jsel["id"])

        if partidos:
            rows = []
            for p in partidos:
                rows.append({
                    "ID":        p["id"],
                    "Local":     p["equipo_local"]["nombre"],
                    "Marcador":  gestor._marcador_partido(p),
                    "Visitante": p["equipo_visitante"]["nombre"],
                    "Estado":    p["estado"],
                    "Fecha":     p["fecha_hora"][:16],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("📋 No hay partidos en esta jornada.")


def show_apuestas(gestor: GestorLiga):
    st.header("🎯 Hacer Apuestas")

    usuarios = gestor.listar_usuarios()
    jornadas = gestor.listar_jornadas(TEMPORADA)
    if not usuarios:
        st.warning("⚠️ No hay usuarios."); return
    if not jornadas:
        st.warning("⚠️ No hay jornadas."); return

    col1, col2 = st.columns([1, 2])
    with col1:
        usuario = st.selectbox("👤 Usuario:", usuarios,
                               format_func=lambda u: gestor.nombre_completo(u))
    with col2:
        jornada = st.selectbox("📅 Jornada:", jornadas,
                               format_func=lambda j: f"Jornada {j['numero']} ({gestor.total_partidos_jornada(j['id'])} partidos)")

    puntaje    = gestor.obtener_o_crear_puntaje(usuario["id"], TEMPORADA)
    disponible = gestor.saldo_disponible(usuario["id"], TEMPORADA)

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown(f"""
        <div class="saldo-box">
            <h3>💰 Saldo Total</h3>
            <h1>{puntaje['puntos_totales']} pts</h1>
        </div>""", unsafe_allow_html=True)
    with col_s2:
        st.markdown(f"""
        <div class="saldo-box" style="background: linear-gradient(135deg, #ff9800, #f44336);">
            <h3>📊 Disponible para apostar</h3>
            <h1>{disponible} pts</h1>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Paso 1: tipo de predicción ─────────────────────────────
    st.subheader("Paso 1 — Selecciona tu tipo de predicción")
    tipos_keys = list(REGLAS.keys())
    if "tipo_sel" not in st.session_state:
        st.session_state["tipo_sel"] = tipos_keys[0]

    tipo_cols = st.columns(3)
    for i, tkey in enumerate(tipos_keys):
        info   = REGLAS[tkey]
        activo = st.session_state["tipo_sel"] == tkey
        cls    = "tipo-card activo" if activo else "tipo-card"
        with tipo_cols[i]:
            st.markdown(f"""
            <div class="{cls}">
                <h4 style="margin:0 0 6px;">{info['label']}</h4>
                <p style="margin:0; font-size:0.82em; color:#555;">{info['desc']}</p>
            </div>""", unsafe_allow_html=True)
            if st.button("Seleccionar", key=f"btn_tipo_{tkey}",
                         use_container_width=True,
                         type="primary" if activo else "secondary"):
                st.session_state["tipo_sel"] = tkey
                st.rerun()

    tipo_seleccionado = st.session_state["tipo_sel"]
    st.markdown("---")

    # ── Paso 2: partido ────────────────────────────────────────
    st.subheader("Paso 2 — Selecciona el partido")
    partidos = gestor.obtener_partidos_jornada(jornada["id"])
    if not partidos:
        st.info("📋 No hay partidos en esta jornada."); return

    partido = st.selectbox(
        "Partido:",
        partidos,
        format_func=lambda p: (
            f"{p['equipo_local']['nombre']} vs {p['equipo_visitante']['nombre']}"
            f"  —  {p['fecha_hora'][:16]}"
        )
    )

    st.markdown(f"""
    <div style="background:#f0f2f6; padding:16px; border-radius:10px; border-left:5px solid #1f77b4;">
        <p style="margin:4px 0; font-size:1.1em;">
            <strong>{partido['equipo_local']['nombre']}</strong>
            <span style="color:#666;"> vs </span>
            <strong>{partido['equipo_visitante']['nombre']}</strong>
        </p>
        <p style="margin:2px 0; color:#666;">📅 {partido['fecha_hora'][:16]}</p>
        <p style="margin:2px 0; color:#666;">🏟️ {partido['equipo_local'].get('estadio') or 'Estadio por confirmar'}</p>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Paso 3: predicción ─────────────────────────────────────
    st.subheader("Paso 3 — Haz tu predicción")
    prediccion = None
    if tipo_seleccionado == "resultado":
        prediccion = _render_resultado(partido)
    elif tipo_seleccionado == "marcador":
        prediccion = _render_marcador(partido)
    elif tipo_seleccionado == "goles_total":
        prediccion = _render_goles_total(partido)

    st.markdown("---")

    # ── Paso 4: puntos a apostar ───────────────────────────────
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

    regla = REGLAS[tipo_seleccionado]
    if "mult" in regla:
        ganancia_max = puntos_apostados * regla["mult"]
        desc_regla   = f"Si aciertas ganas {puntos_apostados} × {regla['mult']} = **{ganancia_max} pts**  |  Si fallas pierdes **{puntos_apostados} pts**"
    else:
        ganancia_max = puntos_apostados + regla["bonus"]
        desc_regla   = f"Si aciertas ganas {puntos_apostados} + {regla['bonus']} = **{ganancia_max} pts**  |  Si fallas pierdes **{puntos_apostados} pts**"
    st.info(f"💡 {desc_regla}")

    st.markdown("---")

    # ── Confirmar ──────────────────────────────────────────────
    if prediccion and puntos_apostados:
        pred_texto = _texto_prediccion(tipo_seleccionado, prediccion, partido)
        ap_prev    = gestor.apuesta_existente(usuario["id"], partido["id"], tipo_seleccionado)
        if ap_prev:
            st.info(f"ℹ️ Ya tienes una apuesta de tipo **{regla['label']}**: "
                    f"**{_texto_prediccion(tipo_seleccionado, ap_prev['prediccion'], partido)}** "
                    f"({ap_prev['puntos_apostados']} pts). Se actualizará al confirmar.")

        st.markdown(f"""
        <div style="background:#e8f5e9; border:2px solid #4caf50; border-radius:10px; padding:16px;">
            <p style="margin:4px 0;"><strong>Tipo:</strong> {regla['label']}</p>
            <p style="margin:4px 0;"><strong>Partido:</strong> {partido['equipo_local']['nombre']} vs {partido['equipo_visitante']['nombre']}</p>
            <p style="margin:4px 0;"><strong>Tu predicción:</strong> {pred_texto}</p>
            <p style="margin:4px 0;"><strong>Puntos apostados:</strong> {puntos_apostados} pts</p>
        </div>""", unsafe_allow_html=True)

        col_btn = st.columns([1, 2, 1])
        with col_btn[1]:
            if st.button("✅ Confirmar Apuesta", type="primary", use_container_width=True):
                try:
                    gestor.hacer_apuesta(usuario["id"], partido["id"],
                                         tipo_seleccionado, prediccion, puntos_apostados)
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


# ── Helpers de predicción ───────────────────────────────────────────────────

def _render_resultado(partido: Dict) -> Optional[str]:
    KEY = "_resultado_sel"
    if KEY not in st.session_state:
        st.session_state[KEY] = None

    opciones = [
        ("1", "🏆 Gana Local",     partido["equipo_local"]["nombre"],     "#f0fff0", "#4caf50", "#2e7d32"),
        ("X", "🤝 Empate",         "Ninguno gana",                        "#fffde7", "#fdd835", "#f9a825"),
        ("2", "🏆 Gana Visitante", partido["equipo_visitante"]["nombre"], "#e3f2fd", "#42a5f5", "#1565c0"),
    ]
    cols = st.columns(3)
    for idx, (val, titulo, subtitulo, bg, borde, color) in enumerate(opciones):
        activo = st.session_state[KEY] == val
        with cols[idx]:
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


def _render_marcador(partido: Dict) -> Optional[str]:
    col1, col2 = st.columns(2)
    with col1:
        gl = st.number_input(f"⚽ Goles {partido['equipo_local']['nombre']}",
                             min_value=0, max_value=10, value=0, key="marc_local")
    with col2:
        gv = st.number_input(f"⚽ Goles {partido['equipo_visitante']['nombre']}",
                             min_value=0, max_value=10, value=0, key="marc_visitante")
    return f"{gl}-{gv}"


def _render_goles_total(partido: Dict) -> Optional[str]:
    st.write("¿Cuántos goles habrá en total en el partido?")
    if "goles_total_sel" not in st.session_state:
        st.session_state["goles_total_sel"] = None

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div style="text-align:center; padding:14px; background:#fff3e0;
             border-radius:12px; border:2px solid #ff9800;">
            <h4 style="margin:0; color:#e65100;">⬇️ Bajo (2 o menos goles)</h4>
        </div>""", unsafe_allow_html=True)
        if st.button("Seleccionar Bajo", use_container_width=True,
                     type="primary" if st.session_state["goles_total_sel"] == "bajo" else "secondary",
                     key="btn_bajo"):
            st.session_state["goles_total_sel"] = "bajo"
            st.rerun()
    with col2:
        st.markdown("""
        <div style="text-align:center; padding:14px; background:#e8eaf6;
             border-radius:12px; border:2px solid #5c6bc0;">
            <h4 style="margin:0; color:#283593;">⬆️ Alto (3 o más goles)</h4>
        </div>""", unsafe_allow_html=True)
        if st.button("Seleccionar Alto", use_container_width=True,
                     type="primary" if st.session_state["goles_total_sel"] == "alto" else "secondary",
                     key="btn_alto"):
            st.session_state["goles_total_sel"] = "alto"
            st.rerun()

    sel = st.session_state.get("goles_total_sel")
    if not sel:
        st.warning("⚠️ Selecciona Bajo u Alto.")
    return sel


def _render_mis_apuestas(gestor: GestorLiga, usuario: Dict, jornada: Dict):
    st.subheader("📋 Mis apuestas en esta jornada")
    apuestas = gestor.apuestas_usuario_jornada(usuario["id"], jornada["id"])
    if not apuestas:
        st.info("📋 Aún no has hecho apuestas en esta jornada."); return

    rows = []
    for ap in apuestas:
        p        = ap["partidos"]
        pred_txt = _texto_prediccion(ap["tipo_apuesta"], ap["prediccion"], p)
        regla    = REGLAS[ap["tipo_apuesta"]]
        acerto   = gestor._acerto_apuesta(ap, p)

        if p["estado"] == "finalizado" and ap.get("puntos_obtenidos") is not None:
            if acerto:
                estado     = "✅ Acertaste"
                puntos_txt = f"+{ap['puntos_obtenidos'] - ap['puntos_apostados']} pts"
            else:
                estado     = "❌ Fallaste"
                puntos_txt = f"-{ap['puntos_apostados']} pts"
            resultado = gestor._marcador_partido(p)
        else:
            estado     = "⏳ Pendiente"
            puntos_txt = "—"
            resultado  = "vs"

        rows.append({
            "Partido":       f"{p['equipo_local']['nombre']} vs {p['equipo_visitante']['nombre']}",
            "Fecha":         p["fecha_hora"][:16],
            "Tipo":          regla["label"],
            "Tu predicción": pred_txt,
            "Resultado":     resultado,
            "Apostado":      f"{ap['puntos_apostados']} pts",
            "Estado":        estado,
            "Ganancia":      puntos_txt,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    total    = len(apuestas)
    aciertos = sum(1 for a in apuestas if gestor._acerto_apuesta(a, a["partidos"]) is True)
    perdidos = sum(a["puntos_apostados"] for a in apuestas if gestor._acerto_apuesta(a, a["partidos"]) is False)
    ganados  = sum((a.get("puntos_obtenidos") or 0) - a["puntos_apostados"]
                   for a in apuestas if gestor._acerto_apuesta(a, a["partidos"]) is True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Apuestas", total)
    c2.metric("Aciertos",       aciertos)
    c3.metric("Ganancia neta",  f"+{ganados} pts")
    c4.metric("Pérdidas",       f"-{perdidos} pts")


def show_clasificacion(gestor: GestorLiga):
    st.header("📊 Clasificación General")
    clasificacion = gestor.obtener_clasificacion(TEMPORADA)
    if not clasificacion:
        st.info("📋 No hay datos de clasificación aún."); return

    st.subheader("🏆 Podio")
    medallas = ["🥇", "🥈", "🥉"]
    cols = st.columns(3)
    for i, p in enumerate(clasificacion[:3]):
        with cols[i]:
            st.markdown(f"""
            <div class="metric-card" style="text-align:center;">
                <h1>{medallas[i]}</h1>
                <h3>{gestor.nombre_completo(p['usuarios'])}</h3>
                <h2>{p['puntos_totales']} pts</h2>
                <p>Aciertos: {p['aciertos']} | Fallos: {p['fallos']}</p>
                <p>Precisión: {_porcentaje_aciertos(p):.1f}%</p>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📋 Clasificación Completa")
    rows = []
    for pos, p in enumerate(clasificacion, 1):
        rows.append({
            "Pos":         pos,
            "Usuario":     gestor.nombre_completo(p["usuarios"]),
            "Saldo (pts)": p["puntos_totales"],
            "Aciertos":    p["aciertos"],
            "Fallos":      p["fallos"],
            "Apuestas":    p["partidos_apostados"],
            "% Acierto":   f"{_porcentaje_aciertos(p):.1f}%"
        })
    df = pd.DataFrame(rows)
    def highlight_top3(row):
        return ["background-color: #fff3cd"] * len(row) if row["Pos"] <= 3 else [""] * len(row)
    st.dataframe(df.style.apply(highlight_top3, axis=1), use_container_width=True, hide_index=True)


def show_admin(gestor: GestorLiga):
    st.header("⚙️ Administración del Sistema")
    tab1, tab2, tab3 = st.tabs(["🔄 Cargar desde API", "🎮 Actualizar Resultados", "📊 Procesar Jornada"])

    # ── TAB 1: Cargar desde API ────────────────────────────────
    with tab1:
        st.subheader("Cargar Datos desde API")

        st.markdown("### 1️⃣ Cargar Equipos")
        st.warning("⚠️ Esto eliminará todos los equipos y partidos existentes.")
        col_api, col_demo = st.columns(2)
        with col_api:
            if st.button("🌐 Cargar Equipos desde API (football-data.org)",
                         type="primary", use_container_width=True):
                with st.spinner("Cargando equipos desde la API…"):
                    try:
                        n = gestor.cargar_equipos_desde_api()
                        st.success(f"✅ {n} equipos cargados desde la API.")
                    except Exception as e:
                        st.error(f"❌ {e}")
        with col_demo:
            if st.button("📋 Cargar Equipos Demo (sin API)", use_container_width=True):
                with st.spinner("Cargando equipos demo…"):
                    try:
                        n = gestor.cargar_equipos_demo()
                        st.success(f"✅ {n} equipos demo cargados.")
                    except Exception as e:
                        st.error(f"❌ {e}")

        st.markdown("---")
        st.markdown("### 2️⃣ Cargar Partidos Futuros desde API")
        st.info(
            "💡 Consulta todos los partidos SCHEDULED de La Liga para cada equipo. "
            "Puede tardar varios minutos (6 seg de espera entre equipos por límite de la API gratuita)."
        )
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.warning("⚠️ Crea una jornada primero en la sección Jornadas.")
        else:
            jsel = st.selectbox("Jornada destino para los partidos:", jornadas,
                                format_func=lambda j: f"Jornada {j['numero']}")
            if st.button("🔄 Cargar Partidos desde API", type="primary"):
                st.warning("⏳ Consultando la API… esto puede tardar varios minutos.")
                try:
                    n = gestor.cargar_partidos_desde_api(jsel["id"])
                    st.success(f"✅ {n} partidos nuevos cargados en Jornada {jsel['numero']}.")
                except Exception as e:
                    st.error(f"❌ {e}")

    # ── TAB 2: Actualizar Resultados ───────────────────────────
    with tab2:
        st.subheader("Actualizar Resultados")
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.warning("⚠️ No hay jornadas.")
        else:
            jsel     = st.selectbox("Jornada:", jornadas,
                                    format_func=lambda j: f"Jornada {j['numero']}", key="j_res")
            partidos = gestor.obtener_partidos_jornada(jsel["id"])
            if partidos:
                partido = st.selectbox("Partido:", partidos,
                    format_func=lambda p: (
                        f"{p['equipo_local']['nombre']} vs {p['equipo_visitante']['nombre']}"
                        f" — {p['fecha_hora'][:16]} ({p['estado']})"
                    ))
                st.markdown(f"""
                <div class="metric-card">
                    <h4>⚽ {partido['equipo_local']['nombre']} vs {partido['equipo_visitante']['nombre']}</h4>
                    <p>📅 {partido['fecha_hora'][:16]} | 🏟️ {partido['equipo_local'].get('estadio') or 'Por confirmar'}</p>
                    <p>Estado: <strong>{partido['estado']}</strong></p>
                </div>""", unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    gl = st.number_input(
                        f"⚽ Goles {partido['equipo_local']['nombre']}",
                        min_value=0, max_value=20,
                        value=partido["goles_local"] if partido.get("goles_local") is not None else 0
                    )
                with col2:
                    gv = st.number_input(
                        f"⚽ Goles {partido['equipo_visitante']['nombre']}",
                        min_value=0, max_value=20,
                        value=partido["goles_visitante"] if partido.get("goles_visitante") is not None else 0
                    )
                if st.button("✅ Actualizar Resultado", type="primary", use_container_width=True):
                    try:
                        gestor.actualizar_resultado(partido["id"], gl, gv)
                        st.success(f"✅ {partido['equipo_local']['nombre']} {gl}-{gv} {partido['equipo_visitante']['nombre']}")
                        time.sleep(1); st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
            else:
                st.info("📋 No hay partidos en esta jornada.")

    # ── TAB 3: Procesar Jornada ────────────────────────────────
    with tab3:
        st.subheader("Procesar Jornada Finalizada")
        st.info("💡 Calcula puntos de todas las apuestas y actualiza los saldos.")
        jornadas = gestor.listar_jornadas(TEMPORADA)
        if not jornadas:
            st.warning("⚠️ No hay jornadas.")
        else:
            jsel = st.selectbox("Jornada:", jornadas,
                                format_func=lambda j: f"Jornada {j['numero']}", key="j_proc")
            if st.button("🎯 Procesar Jornada", type="primary"):
                with st.spinner("Procesando…"):
                    try:
                        res = gestor.procesar_jornada(jsel["id"], TEMPORADA)
                        st.success(f"""
                        ✅ Jornada procesada:
                        - Apuestas procesadas: {res['apuestas_procesadas']}
                        - Puntos ganados: +{res['puntos_otorgados']}
                        - Puntos perdidos: -{res['puntos_perdidos']}
                        """)
                    except Exception as e:
                        st.error(f"❌ {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    st.markdown('<div class="main-header">⚽ LA POLLA - LIGA ESPAÑOLA</div>', unsafe_allow_html=True)
    gestor = get_gestor()

    st.sidebar.title("📋 Menú Principal")
    st.sidebar.markdown("---")

    menu = {
        "🏠 Dashboard":       "dashboard",
        "⚽ Equipos":         "equipos",
        "👥 Usuarios":        "usuarios",
        "📅 Jornadas":        "jornadas",
        "🎯 Hacer Apuestas":  "apuestas",
        "📊 Clasificación":   "clasificacion",
        "⚙️ Administración":  "admin",
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


if __name__ == "__main__":
    main()