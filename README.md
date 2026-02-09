# ⚽ La Polla - Liga Española

Sistema de quinielas para La Liga española desarrollado con Streamlit.

## 🎮 Características

- **Dashboard** con métricas generales y clasificación
- **Gestión de equipos** de La Liga (20 equipos incluidos)
- **Sistema de usuarios** con registro y seguimiento de puntos
- **Gestión de jornadas** y partidos
- **Sistema de apuestas** con 3 tipos:
  - **Resultado** (1/X/2) - Multiplicador x2
  - **Marcador exacto** - Multiplicador x3
  - **Total de goles** (Bajo ≤2 / Alto ≥3) - Bonus +5 pts
- **Clasificación** con podio y estadísticas

## 🚀 Deploy en Streamlit Cloud

### Paso 1: Subir a GitHub

```bash
# Clonar o inicializar repositorio
git init
git add .
git commit -m "Initial commit - La Polla Liga Española"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/la-polla-liga.git
git push -u origin main
```

### Paso 2: Deploy en Streamlit Cloud

1. Ve a [share.streamlit.io](https://share.streamlit.io)
2. Inicia sesión con tu cuenta de GitHub
3. Click en **"New app"**
4. Selecciona:
   - **Repository:** `TU-USUARIO/la-polla-liga`
   - **Branch:** `main`
   - **Main file path:** `app.py`
5. Click en **"Deploy"**

Tu app estará disponible en: `https://tu-usuario-la-polla-liga.streamlit.app`

## 📁 Estructura del Proyecto

```
la-polla-liga/
├── app.py                  # Aplicación principal
├── requirements.txt        # Dependencias Python
├── README.md              # Este archivo
├── .gitignore             # Archivos a ignorar
└── .streamlit/
    └── config.toml        # Configuración de Streamlit
```

## 🔧 Ejecución Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
streamlit run app.py
```

## 📋 Notas

- La base de datos SQLite (`la_polla.db`) se crea automáticamente
- Los equipos de La Liga están pre-cargados (temporada 2025-2026)
- Cada usuario inicia con **100 puntos**
- Las apuestas pueden ser de **5, 10, 15 o 20 puntos**

## 🎯 Reglas de Puntuación

| Tipo de Apuesta | Descripción | Ganancia |
|-----------------|-------------|----------|
| Resultado (1/X/2) | Predice ganador o empate | Apuesta × 2 |
| Marcador Exacto | Acierta el marcador exacto | Apuesta × 3 |
| Total de Goles | Bajo (≤2) o Alto (≥3) | Apuesta + 5 |

---

Desarrollado con ❤️ usando [Streamlit](https://streamlit.io/)
