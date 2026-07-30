import json
import os
import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium

st.set_page_config(page_title="23/08/2026 Pedal Piratuba", layout="wide")

SHEET_ID = "1lwExfW6GPS198QuLNfvJN8LzWEvms4_1bgoB-ogNq00"

ABAS = {
    "GERAL": None,
    "LIGHT": 1307686260,
    "EBIKE": 979975317,
    "SPORT FEM": 2081351294,
    "SPORT MAS": 310681045,
    "PRO FEM": 250811187,
    "PRO MAS": 1318274495,
    "City Tour dia 22/08": 971261230,
}

CACHE_FILE = "coordenadas_cache.json"

CORES_ESTADOS = {
    "PR": "#E74C3C",  # Vermelho
    "RS": "#2ECC71",  # Verde
    "SC": "#3498DB",  # Azul
}
COR_PADRAO = "#95A5A6"


def carregar_cache_coordenadas():
  if os.path.exists(CACHE_FILE):
    try:
      with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return {}
  return {}


def salvar_cache_coordenadas(cache):
  try:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
      json.dump(cache, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


@st.cache_data(ttl=86400)
def obter_coordenadas_automatico(lista_chaves):
  cache = carregar_cache_coordenadas()
  geolocator = Nominatim(user_agent="pedal_piratuba_app_v3", timeout=5)
  geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.0)

  atualizou_cache = False

  for chave in lista_chaves:
    if not chave or pd.isna(chave) or chave in cache:
      continue

    try:
      location = geocode(f"{chave}, Brasil")
      if location:
        cache[chave] = [location.latitude, location.longitude]
        atualizou_cache = True
    except Exception:
      pass

  if atualizou_cache:
    salvar_cache_coordenadas(cache)

  return cache


@st.cache_data(ttl=60)
def carregar(gid):
  url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
  df = pd.read_csv(url, header=1)
  df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
  df.columns = df.columns.astype(str).str.strip()

  # 1. Remove linhas totalmente vazias (todos os valores nulos/NaN)
  df = df.dropna(how="all")

  # 2. Remove linhas onde todas as células são vazias ou contêm apenas espaços
  linhas_validas = df.apply(
      lambda row: row.astype(str).str.strip().str.len().sum() > 0, axis=1
  )
  df = df[linhas_validas]

  return df


def encontrar_coluna(df, nomes_possiveis):
  for col in df.columns:
    for nome in nomes_possiveis:
      if nome.lower() in col.lower():
        return col
  return None


# --- BOTÕES DE NAVEGAÇÃO POR CATEGORIA ---
categoria = st.segmented_control(
    "Utilize os Filtros:", options=list(ABAS.keys()), default="GERAL"
)

if not categoria:
  categoria = "GERAL"


# --- CARREGAMENTO DOS DADOS ---
if categoria == "GERAL":
  dfs = []
  for nome, gid in ABAS.items():
    if gid is None:
      continue
    try:
      temp = carregar(gid)
      if not temp.empty:
        temp["Categoria"] = nome
        dfs.append(temp)
    except Exception:
      pass
  df = pd.concat(dfs, ignore_index=True) if len(dfs) > 0 else pd.DataFrame()
else:
  df = carregar(ABAS[categoria])


df.columns = df.columns.str.strip()

# --- TRATAMENTO GLOBAL PARA REMOVER 'None', 'NaN' E VALORES NULOS ---
df = df.fillna("")
df = df.replace(["None", "none", "nan", "NaN"], "")

# Garante a filtragem global de linhas em que todas as colunas ficaram em branco após a substituição
if not df.empty:
  df = df[df.apply(lambda row: row.astype(str).str.strip().ne("").any(), axis=1)]

col_cidade = encontrar_coluna(df, ["cidade", "municipio"])
col_estado = encontrar_coluna(df, ["uf", "estado"])


# --- KPI CONTADOR ---
st.write("")
c1, c2 = st.columns([1, 4])

with c1:
  st.metric("Total de Inscritos", len(df))

st.divider()

col1, col2 = st.columns(2)


# --- BLOCO 1: TOP 10 CIDADES ---
with col1:
  if (
      col_cidade
      and col_estado
      and col_cidade in df.columns
      and col_estado in df.columns
  ):
    dados_barras = df.copy()

    dados_barras[col_cidade] = (
        dados_barras[col_cidade].astype(str).str.strip()
    )
    dados_barras[col_estado] = (
        dados_barras[col_estado].astype(str).str.strip().str.upper()
    )

    filtro_validos = (
        dados_barras[col_cidade].ne("")
        & dados_barras[col_cidade].ne("-")
        & dados_barras[col_estado].ne("")
        & dados_barras[col_estado].ne("-")
    )

    dados_filtrados = dados_barras[filtro_validos].copy()

    dados_filtrados["CidadeUF"] = (
        dados_filtrados[col_cidade].str.upper()
        + " "
        + dados_filtrados[col_estado]
    )

    dados_top = (
        dados_filtrados["CidadeUF"]
        .value_counts()
        .head(10)
        .reset_index()
    )

    dados_top.columns = ["Cidade", "Quantidade"]

    fig = px.bar(
        dados_top,
        x="Quantidade",
        y="Cidade",
        orientation="h",
        text="Quantidade",
        title="Top 10 Cidades",
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        yaxis_title="",
        xaxis_title="Inscritos",
        showlegend=False,
        margin=dict(l=10, r=40, t=50, b=10),
    )

    st.plotly_chart(fig, use_container_width=True)
  else:
    st.info("Colunas de localidade não encontradas para o gráfico.")


# --- BLOCO 2: MAPA DO BRASIL ---
with col2:
  st.subheader("📍 Origem dos Inscritos")

  if (
      col_cidade
      and col_estado
      and col_cidade in df.columns
      and col_estado in df.columns
  ):
    df_mapa_clean = df.copy()
    df_mapa_clean[col_cidade] = (
        df_mapa_clean[col_cidade].astype(str).str.strip().str.upper()
    )
    df_mapa_clean[col_estado] = (
        df_mapa_clean[col_estado].astype(str).str.strip().str.upper()
    )

    filtro_mapa = (
        df_mapa_clean[col_cidade].ne("")
        & df_mapa_clean[col_cidade].ne("-")
        & df_mapa_clean[col_estado].ne("")
        & df_mapa_clean[col_estado].ne("-")
    )

    df_mapa = (
        df_mapa_clean[filtro_mapa]
        .groupby([col_cidade, col_estado])
        .size()
        .reset_index(name="Quantidade")
    )

    df_mapa["Chave"] = df_mapa[col_cidade] + ", " + df_mapa[col_estado]

    chaves_unicas = df_mapa["Chave"].unique().tolist()
    coordenadas_dict = obter_coordenadas_automatico(chaves_unicas)

    m = folium.Map(
        location=[-26.5, -51.5], zoom_start=6, tiles="cartodbpositron"
    )

    for _, row in df_mapa.iterrows():
      chave = row["Chave"]
      qtd = row["Quantidade"]
      cid = row[col_cidade]
      uf = row[col_estado]

      if chave in coordenadas_dict:
        lat, lon = coordenadas_dict[chave]
        cor_marcador = CORES_ESTADOS.get(uf, COR_PADRAO)
        raio = 6 + (qtd * 1.2)

        folium.CircleMarker(
            location=[lat, lon],
            radius=min(raio, 25),
            popup=f"<b>{cid} - {uf}</b><br>{qtd} inscrito(s)",
            tooltip=f"{cid} - {uf}: {qtd} inscritos",
            color=cor_marcador,
            fill=True,
            fill_color=cor_marcador,
            fill_opacity=0.7,
            weight=1.5,
        ).add_to(m)

    st_folium(m, height=400, use_container_width=True, key="mapa_sul_dinamico")

    st.markdown(
        """
            <div style="display: flex; gap: 15px; font-size: 13px; font-weight: bold; margin-top: 5px;">
                <span style="color: #3498DB;">🔵 SC (Azul)</span>
                <span style="color: #2ECC71;">🟢 RS (Verde)</span>
                <span style="color: #E74C3C;">🔴 PR (Vermelho)</span>
            </div>
            """,
        unsafe_allow_html=True,
    )

  else:
    st.warning("Colunas de Cidade/UF não identificadas.")


# --- TABELA DE INSCRITOS ---
st.subheader("Inscritos")

styler = df.style.set_table_styles(
    [{"selector": "th", "props": [("font-weight", "bold")]}]
)

st.dataframe(styler, hide_index=True, use_container_width=True)
