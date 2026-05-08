"""SIOPS – Consulta de Despesas por Subfunção (Streamlit web app)."""

import base64
import io
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from api import SIOPSClient

# ── Logo helper ───────────────────────────────────────────────────────────────
_ASSETS = Path(__file__).parent / "assets"

def _logo_html() -> str:
    """Return an <img> tag with the SIOPS logo (PNG preferred, SVG fallback)."""
    for name, mime in [("logo_siops.png", "image/png"), ("logo_siops.svg", "image/svg+xml")]:
        path = _ASSETS / name
        if path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode()
            return (
                f'<img src="data:{mime};base64,{b64}" '
                f'style="width:100%; max-width:230px; margin: 8px auto 4px auto; display:block;" '
                f'alt="SIOPS"/>'
            )
    return '<div style="color:#fff;font-size:1.6rem;font-weight:900;">🏥 SIOPS</div>'


# ── Helpers ───────────────────────────────────────────────────────────────────

def enrich_df(
    df: pd.DataFrame,
    estados: List[Dict],
    anos_periodos: List[Dict],
    muni_cache: Dict[str, List[Dict]],
) -> pd.DataFrame:
    """Map numeric codes to human-readable labels and clean up the DataFrame."""
    if df.empty:
        return df

    df = df.copy()

    # UF: numeric code → "SP – São Paulo"
    uf_map = {e["co_uf"]: f"{e['sg_uf']} – {e['no_uf']}" for e in estados}
    if "UF" in df.columns:
        df["UF"] = df["UF"].map(uf_map).fillna(df["UF"])

    # Município: numeric co_municipio → name (from cache)
    muni_map: Dict[str, str] = {}
    for sg_uf, munis in muni_cache.items():
        for m in munis:
            muni_map[str(m["co_municipio"])] = m["no_municipio"]
    if "Município" in df.columns:
        df["Município"] = df["Município"].map(
            lambda v: muni_map.get(str(v), v) if pd.notna(v) else "—"
        )

    # Período: numeric code → descriptive label ("6º Bimestre")
    periodo_desc = {ap["periodo"]: ap["dsPeriodo"] for ap in anos_periodos}
    if "Período" in df.columns:
        df["Período"] = df["Período"].map(periodo_desc).fillna(df["Período"])

    return df


# ── Page config ───────────────────────────────────────────────────────────────
_favicon = str(_ASSETS / "logo_siops.png") if (_ASSETS / "logo_siops.png").exists() else "🏥"
st.set_page_config(
    page_title="SIOPS – Despesas por Subfunção",
    page_icon=_favicon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ── Page background ─────────────────────────────────── */
    .stApp { background-color: #F7F9FC; }
    .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1400px; }

    /* ── Sidebar ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: linear-gradient(175deg, #2D3748 0%, #1A202C 50%, #0D1117 100%);
        border-right: none;
    }
    [data-testid="stSidebar"] * { color: #E8F1FF !important; }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] label { color: #CBD8F0 !important; }
    [data-testid="stSidebar"] [data-testid="stSelectboxLabel"],
    [data-testid="stSidebar"] .stMultiSelect label { color: #A0AEC0 !important; font-weight: 600 !important; font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.05em; }

    /* Sidebar inputs */
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background-color: rgba(255,255,255,0.12) !important;
        border-color: rgba(255,255,255,0.2) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] span { color: #fff !important; }

    /* Multiselect tags — blue pill instead of red */
    [data-baseweb="tag"] {
        background-color: rgba(255,255,255,0.22) !important;
        border-radius: 6px !important;
    }
    [data-baseweb="tag"] span { color: #fff !important; }
    [data-testid="stSidebar"] [data-baseweb="tag"] {
        background-color: rgba(255,255,255,0.25) !important;
    }

    /* Sidebar radio */
    [data-testid="stSidebar"] [data-testid="stRadio"] label { font-size: 0.92rem !important; }

    /* Sidebar divider */
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.18) !important; }

    /* Sidebar buttons */
    [data-testid="stSidebar"] .stButton button {
        background-color: rgba(255,255,255,0.15) !important;
        color: #fff !important;
        border: 1px solid rgba(255,255,255,0.3) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: background 0.2s;
    }
    [data-testid="stSidebar"] .stButton button:hover {
        background-color: rgba(255,255,255,0.25) !important;
    }
    /* Botão primário (Buscar Dados) — cobre todas as versões do Streamlit */
    [data-testid="stSidebar"] button[kind="primary"],
    [data-testid="stSidebar"] button[kind="primary"] p,
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p,
    [data-testid="stSidebar"] [data-testid="stButton"] button:first-child,
    [data-testid="stSidebar"] [data-testid="stButton"] button:first-child p {
        background-color: #1565C0 !important;
        color: #FFFFFF !important;
        border: 2px solid rgba(255,255,255,0.35) !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        border-radius: 8px !important;
    }

    /* ── Metric cards ────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: #FFFFFF;
        border: 1px solid #DDE6F5;
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(21,101,192,0.07);
    }
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {
        font-size: 0.78rem;
        font-weight: 600;
        color: #5C7BB5;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1A2F5A;
    }

    /* ── Section headings ────────────────────────────────── */
    h3 { color: #1A3A6B !important; font-weight: 700 !important; }

    /* ── Dataframe ───────────────────────────────────────── */
    [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid #DDE6F5; }

    /* ── Download buttons ────────────────────────────────── */
    [data-testid="stDownloadButton"] button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.2rem !important;
        border: 1.5px solid #1565C0 !important;
        color: #1565C0 !important;
        background: #fff !important;
        transition: all 0.2s !important;
    }
    [data-testid="stDownloadButton"] button:hover {
        background: #1565C0 !important;
        color: #fff !important;
    }

    /* ── Expander (errors) ───────────────────────────────── */
    [data-testid="stExpander"] { border-radius: 10px !important; border: 1px solid #FBBF24 !important; }

    /* ── Divider ─────────────────────────────────────────── */
    hr { border-color: #E2EBF8 !important; }

    /* ── Radio pills ─────────────────────────────────────── */
    [data-testid="stRadio"] [data-baseweb="radio"] { gap: 0.4rem; }

    </style>
    """,
    unsafe_allow_html=True,
)

# ── API client (shared across sessions) ───────────────────────────────────────
@st.cache_resource
def _get_client() -> SIOPSClient:
    return SIOPSClient()


client = _get_client()


# ── Cached reference data (refreshed every hour) ──────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Carregando estados…")
def load_estados() -> List[Dict]:
    return sorted(client.get_estados(), key=lambda e: e["sg_uf"])


@st.cache_data(ttl=3600, show_spinner="Carregando períodos…")
def load_anos_periodos() -> List[Dict]:
    return client.get_anos_periodos()


@st.cache_data(ttl=3600, show_spinner=False)
def load_municipios(co_uf: str) -> List[Dict]:
    return client.get_municipios(co_uf)


# ── Session state defaults ────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state["df"] = pd.DataFrame()
if "errors" not in st.session_state:
    st.session_state["errors"] = []


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"""
        <div style="padding: 0.8rem 0.5rem 0.4rem 0.5rem; text-align:center;">
            {_logo_html()}
            <div style="font-size:0.72rem; color:#90CDF4; margin-top:6px; line-height:1.5; letter-spacing:0.02em;">
                Despesas por Subfunção
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    # Load reference data
    try:
        estados = load_estados()
        anos_periodos = load_anos_periodos()
    except Exception as exc:
        st.error(f"❌ Erro ao conectar à API do SIOPS:\n\n{exc}")
        st.stop()

    # ── Nível de Consulta ─────────────────────────────────────────────────────
    st.markdown("**Nível de Consulta**")
    nivel = st.radio(
        "nivel",
        options=["Estadual", "Municipal"],
        horizontal=True,
        label_visibility="collapsed",
    )

    # ── Estados ───────────────────────────────────────────────────────────────
    _ALL = "☑ Selecionar todos"
    estado_map: Dict[str, Dict] = {
        f"{e['sg_uf']} – {e['no_uf']}": e for e in estados
    }
    todas_opcoes_estados = list(estado_map.keys())

    # Se "Selecionar todos" estiver na seleção, substitui por todos os estados reais e reroda
    if _ALL in st.session_state.get("ms_estados", []):
        st.session_state["ms_estados"] = todas_opcoes_estados
        st.rerun()

    selected_estado_labels = st.multiselect(
        "**Estados (UF)**",
        options=[_ALL] + todas_opcoes_estados,
        placeholder="Selecione estados…",
        key="ms_estados",
    )
    selected_estados = [estado_map[k] for k in selected_estado_labels]

    # ── Municípios (logo abaixo dos estados, só quando Municipal) ─────────────
    selected_munis: List[Dict] = []
    if nivel == "Municipal":
        if not selected_estados:
            st.info("Selecione ao menos um estado para listar municípios.")
        else:
            with st.spinner("Carregando municípios…"):
                all_munis: List[Dict] = []
                for estado in selected_estados:
                    try:
                        for m in load_municipios(estado["co_uf"]):
                            all_munis.append(
                                {
                                    "co_uf": estado["co_uf"],
                                    "sg_uf": estado["sg_uf"],
                                    "co": str(m["co_municipio"]),
                                    "nome": m["no_municipio"],
                                    "label": f"{estado['sg_uf']} – {m['no_municipio']}",
                                }
                            )
                    except Exception as exc:
                        st.warning(
                            f"Erro ao carregar municípios de {estado['sg_uf']}: {exc}"
                        )
            all_munis.sort(key=lambda x: x["label"])
            if "muni_cache" not in st.session_state:
                st.session_state["muni_cache"] = {}
            for estado in selected_estados:
                st.session_state["muni_cache"][estado["sg_uf"]] = (
                    load_municipios(estado["co_uf"])
                )
            muni_map = {m["label"]: m for m in all_munis}
            todas_opcoes_munis = list(muni_map.keys())

            # Se "Selecionar todos" estiver na seleção, substitui por todos os municípios reais e reroda
            if _ALL in st.session_state.get("ms_munis", []):
                st.session_state["ms_munis"] = todas_opcoes_munis
                st.rerun()

            selected_muni_labels = st.multiselect(
                "**Municípios**",
                options=[_ALL] + todas_opcoes_munis,
                placeholder=f"Selecione municípios… ({len(all_munis)} disponíveis)",
                key="ms_munis",
            )
            selected_munis = [muni_map[k] for k in selected_muni_labels]

    # ── Anos (2018–2026 apenas) ────────────────────────────────────────────────
    anos_unicos = sorted(
        {ap["ano"] for ap in anos_periodos if "2018" <= ap["ano"] <= "2026"},
        reverse=True,
    )
    selected_anos = st.multiselect(
        "**Anos**",
        options=anos_unicos,
        default=[],
        placeholder="Selecione anos…",
    )

    # ── Períodos (filtrado pelos anos selecionados) ────────────────────────────
    periodo_map: Dict[str, Dict] = {}
    for ap in anos_periodos:
        if ap["ano"] in selected_anos:
            label = f"{ap['ano']} – {ap['dsPeriodo']}"
            if label not in periodo_map:
                periodo_map[label] = ap

    selected_periodo_labels = st.multiselect(
        "**Períodos**",
        options=list(periodo_map.keys()),
        default=[],
        placeholder="Selecione períodos…",
    )
    selected_periodos = [periodo_map[k] for k in selected_periodo_labels]

    st.divider()

    # ── Fetch button ──────────────────────────────────────────────────────────
    can_fetch = bool(selected_estados and selected_periodos)
    if nivel == "Municipal":
        can_fetch = can_fetch and bool(selected_munis)

    fetch_clicked = st.button(
        "🔍 Buscar Dados",
        type="primary",
        use_container_width=True,
        disabled=not can_fetch,
    )
    # JS garante a cor independente da versão do Streamlit
    st.markdown(
        """
        <script>
        (function() {
            const btn = window.parent.document.querySelector(
                '[data-testid="stSidebar"] button[kind="primary"]'
            );
            if (btn) {
                btn.style.setProperty('background-color', '#1565C0', 'important');
                btn.style.setProperty('color', '#FFFFFF', 'important');
                btn.style.setProperty('border', '2px solid rgba(255,255,255,0.5)', 'important');
                btn.style.setProperty('font-weight', '700', 'important');
            }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

    if not can_fetch:
        if not selected_estados:
            st.caption("⚠️ Selecione ao menos um estado.")
        elif not selected_periodos:
            st.caption("⚠️ Selecione ao menos um período.")
        elif nivel == "Municipal" and not selected_munis:
            st.caption("⚠️ Selecione ao menos um município.")

    # Clear button
    if not st.session_state["df"].empty:
        if st.button("🗑️ Limpar resultados", use_container_width=True):
            st.session_state["df"] = pd.DataFrame()
            st.session_state["errors"] = []
            st.rerun()


# ── Main area — fetch logic ───────────────────────────────────────────────────
if fetch_clicked:
    tasks = []
    if nivel == "Estadual":
        for estado in selected_estados:
            for per in selected_periodos:
                tasks.append(("estadual", estado["co_uf"], per["ano"], per["periodo"]))
    else:
        for muni in selected_munis:
            for per in selected_periodos:
                tasks.append(
                    ("municipal", muni["co_uf"], muni["co"], per["ano"], per["periodo"])
                )

    progress_bar = st.progress(0.0, text=f"Iniciando consulta de {len(tasks)} combinação(ões)…")
    status_text = st.empty()

    def _progress_cb(done: int, total: int) -> None:
        pct = done / total
        progress_bar.progress(pct, text=f"Buscando… {done}/{total} concluído(s)")

    df, errors = client.fetch_all(tasks, progress_cb=_progress_cb)

    progress_bar.empty()
    status_text.empty()

    df = enrich_df(df, estados, anos_periodos, st.session_state.get("muni_cache", {}))
    st.session_state["df"] = df
    st.session_state["errors"] = errors


# ── Main area — results ───────────────────────────────────────────────────────
df: pd.DataFrame = st.session_state["df"]
errors: List[str] = st.session_state["errors"]

# Error panel
if errors:
    with st.expander(f"⚠️ {len(errors)} requisição(ões) com erro — clique para ver", expanded=False):
        for err in errors:
            st.code(err, language=None)

# Empty state
if df.empty:
    st.markdown(
        """
        <div style="
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 62vh; gap: 1.2rem;
        ">
            <div style="
                background: #EFF4FB; border-radius: 50%; width: 96px; height: 96px;
                display: flex; align-items: center; justify-content: center;
                font-size: 2.8rem; box-shadow: 0 4px 20px rgba(21,101,192,0.12);
            ">🏥</div>
            <h2 style="margin: 0; color: #1A3A6B; font-weight: 700;">SIOPS — Despesas por Subfunção</h2>
            <p style="margin: 0; font-size: 1rem; color: #5C7BB5; text-align:center; max-width:400px; line-height:1.6;">
                Selecione os <b>estados</b>, <b>anos</b> e <b>períodos</b> na barra lateral
                e clique em <b>Buscar Dados</b> para visualizar os dados consolidados.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ── Metrics ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:0.5rem;">
        <div style="width:4px; height:28px; background:#1565C0; border-radius:4px;"></div>
        <h3 style="margin:0;">Resumo da Consulta</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

TOTAL_COL = "TOTAL"
valor_cols = [c for c in df.columns if c not in ("UF", "Município", "Ano", "Período", "Subfunção")]
total_geral = df[TOTAL_COL].sum() if TOTAL_COL in df.columns else 0
n_ufs   = df["UF"].nunique()       if "UF"        in df.columns else 0
n_munis_val = df["Município"].replace("—", pd.NA).dropna().nunique() if "Município" in df.columns else 0
n_subfuncoes = df["Subfunção"].nunique() if "Subfunção" in df.columns else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📋 Registros", f"{len(df):,}")
c2.metric("🗺️ UFs", n_ufs)
c3.metric("🏙️ Municípios", n_munis_val if n_munis_val > 0 else "—")
c4.metric("📌 Subfunções únicas", n_subfuncoes)
c5.metric("💰 Total Geral (R$)", f"{total_geral:,.0f}")

st.markdown("<div style='margin-bottom:1.2rem'></div>", unsafe_allow_html=True)
st.divider()

# ── View toggle ───────────────────────────────────────────────────────────────
col_view, col_info = st.columns([3, 5])
with col_view:
    view = st.radio(
        "Visualização",
        options=["Dados Brutos", "Consolidado por Subfunção"],
        horizontal=True,
        label_visibility="collapsed",
    )

if view == "Consolidado por Subfunção":
    group_cols = [c for c in ["UF", "Município", "Ano", "Período", "Subfunção"] if c in df.columns]
    agg_cols = {c: "sum" for c in valor_cols if c in df.columns}
    display_df = df.groupby(group_cols, as_index=False, dropna=False).agg(agg_cols)
    with col_info:
        st.caption(f"🔢 {len(display_df):,} linhas após consolidação")
else:
    display_df = df
    with col_info:
        st.caption(f"🔢 {len(display_df):,} linhas no total")

# ── Data table ────────────────────────────────────────────────────────────────
money_cols = {
    col: st.column_config.NumberColumn(col, format="R$ %.2f")
    for col in valor_cols
    if col in display_df.columns
}
st.dataframe(
    display_df,
    use_container_width=True,
    height=460,
    hide_index=True,
    column_config={
        **money_cols,
        "Ano":       st.column_config.TextColumn("Ano"),
        "Período":   st.column_config.TextColumn("Período"),
        "UF":        st.column_config.TextColumn("UF"),
        "Município": st.column_config.TextColumn("Município"),
        "Subfunção": st.column_config.TextColumn("Subfunção", width="large"),
    },
)

# ── Export ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    """
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:0.5rem;">
        <div style="width:4px; height:28px; background:#1565C0; border-radius:4px;"></div>
        <h3 style="margin:0;">Exportar Dados</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

exp_c1, exp_c2, exp_c3 = st.columns(3)

with exp_c1:
    csv_bytes = display_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 Baixar CSV",
        data=csv_bytes,
        file_name="siops_export.csv",
        mime="text/csv",
        use_container_width=True,
    )

with exp_c2:
    xlsx_buf = io.BytesIO()
    with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
        display_df.to_excel(writer, index=False, sheet_name="SIOPS")
        ws = writer.sheets["SIOPS"]
        for col_cells in ws.columns:
            max_len = max(
                (len(str(cell.value)) for cell in col_cells if cell.value), default=8
            )
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 45)
    st.download_button(
        label="📥 Baixar XLSX",
        data=xlsx_buf.getvalue(),
        file_name="siops_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with exp_c3:
    json_bytes = display_df.to_json(
        orient="records", force_ascii=False, indent=2
    ).encode("utf-8")
    st.download_button(
        label="📥 Baixar JSON",
        data=json_bytes,
        file_name="siops_export.json",
        mime="application/json",
        use_container_width=True,
    )
