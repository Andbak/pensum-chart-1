import io
import time
import requests
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, date, timedelta

# ------------------ KONFIG ------------------ #
CSV_URL_DEFAULT = ("https://docs.google.com/spreadsheets/d/e/"
                   "2PACX-1vSvskjfFaBMj251I0ejyarPl6tRVnRFUI2Xa9hCPf41pndkg2hcB63jJEw-eeur8VuXNZO9KddBIC18/pub?output=csv")

PENSUM_NAVY = "#0a2843"
MUTED_BG = "#f1f4f6"
CARD_BG  = "#ffffff"
BORDER   = "#e6ebef"
RADIUS   = "16px"

st.set_page_config(
    page_title="Pensum – Avkastning",
    page_icon="📈",
    layout="wide",
    menu_items={"Get Help": None, "Report a bug": None, "About": None}
)

# Skjul Streamlit-header/footer (i tillegg til ?embed=true)
st.markdown("""
<style>
#MainMenu, header, footer {visibility: hidden;}
[data-testid="stAppViewContainer"] {background: %s;}
.card{
  background:%s;border:1px solid %s;border-radius:%s;
  box-shadow:0 8px 24px rgba(0,0,0,.06); overflow:hidden;
}
.card-header{
  background:%s;color:#fff;padding:16px 20px;font-weight:700;letter-spacing:.2px;
}
.card-body{ padding: 16px; }
</style>
""" % (MUTED_BG, CARD_BG, BORDER, RADIUS, PENSUM_NAVY), unsafe_allow_html=True)

# ------------------ HJELPEFUNKSJONER ------------------ #
@st.cache_data(ttl=300, show_spinner=False)
def fetch_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    # Google CSV kan ha NBSP og lokale tusenskilletegn/komma
    text = r.text.replace("\u00A0","").replace("\xa0","")
    df = pd.read_csv(io.StringIO(text))
    return df

def coerce_numbers(s: pd.Series) -> pd.Series:
    # fjerner mellomrom og bytter komma til punktum før konvertering
    return pd.to_numeric(
        s.astype(str).str.replace(" ", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce"
    )

def tidy_df(df: pd.DataFrame) -> pd.DataFrame:
    # Forventer "Date" + kolonner for fond/indekser
    # Normaliser navn (strip)
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    # Dato
    if "Date" not in df.columns:
        raise ValueError("Fant ikke kolonnen 'Date' i CSV.")
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    # Tallkolonner
    for c in df.columns:
        if c == "Date": continue
        df[c] = coerce_numbers(df[c])
    # Fjern tomme datoer
    df = df.dropna(subset=["Date"]).sort_values("Date")
    return df

def filter_period(df: pd.DataFrame, period_key: str) -> pd.DataFrame:
    if df.empty: return df
    end = df["Date"].max()
    if period_key == "1M":
        start = end - pd.DateOffset(months=1)
    elif period_key == "3M":
        start = end - pd.DateOffset(months=3)
    elif period_key == "YTD":
        start = pd.Timestamp(end.year, 1, 1)
    elif period_key == "1Y":
        start = end - pd.DateOffset(years=1)
    else:  # "MAX"
        start = df["Date"].min()
    return df.loc[df["Date"].between(start, end)]

def normalize_from_first(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Returnerer % endring fra første dato i DF for hver valgt kolonne."""
    out = df[["Date"]].copy()
    for c in cols:
        s = df[c].dropna()
        if s.empty:
            out[c] = pd.NA
            continue
        base = s.iloc[0]
        out[c] = (df[c] / base - 1.0) * 100.0
    return out

def pensum_chart(df_pct: pd.DataFrame, cols: list):
    df_long = df_pct.melt("Date", value_vars=cols, var_name="Serie", value_name="Endring (%)")
    # Altair-tema
    chart = (
        alt.Chart(df_long)
          .mark_line(point=False, strokeWidth=2)
          .encode(
              x=alt.X("Date:T", title="Dato"),
              y=alt.Y("Endring (%):Q", title="Utvikling fra startdato", axis=alt.Axis(format="~s")),
              color=alt.Color("Serie:N", title=None),
              tooltip=[alt.Tooltip("Date:T", title="Dato"),
                       alt.Tooltip("Serie:N"),
                       alt.Tooltip("Endring (%):Q", format=".2f")]
          )
          .properties(height=420, background="white")
          .configure_axis(labelColor="#0f172a", titleColor="#0f172a")
          .configure_legend(
              orient="top",
              direction="horizontal",
              labelColor="#0f172a",
              symbolStrokeWidth=10,
              padding=6
          )
    )
    return chart

# ------------------ UI ------------------ #
st.markdown('<div class="card"><div class="card-header">Pensum fond – Avkastning i NOK</div><div class="card-body">', unsafe_allow_html=True)

csv_url = st.text_input(
    "Google Sheets CSV-lenke",
    value=CSV_URL_DEFAULT,
    help="Fra Google Sheets: Fil → Del → Publiser på web → velg ark → CSV."
)

col_a, col_b = st.columns([1,1])

with col_a:
    period = st.segmented_control(
        "Periode",
        options=["1M", "3M", "YTD", "1Y", "MAX"],
        default="YTD",
    )
with col_b:
    st.write("")  # spacing
    st.write("")

# last data
error = None
try:
    df_raw = fetch_csv(csv_url)
    df = tidy_df(df_raw)
except Exception as e:
    error = str(e)

if error:
    st.error(f"Kunne ikke laste data: {error}")
else:
    # velg serier
    all_series = [c for c in df.columns if c != "Date"]
    default_pick = [s for s in all_series if "Pensum" in s][:3] or all_series[:3]
    picked = st.multiselect(
        "Velg fond/indekser",
        options=all_series,
        default=default_pick
    )

    # Filter + normaliser
    dff = filter_period(df, period)
    if dff.empty or not picked:
        st.info("Ingen data i valgt periode/utvalg.")
    else:
        dfn = normalize_from_first(dff, picked)
        chart = pensum_chart(dfn, picked)
        st.altair_chart(chart, use_container_width=True)

        # Liten tabell under grafen (valgfritt)
        show_tbl = st.checkbox("Vis tabell for valgt periode", value=False)
        if show_tbl:
            df_show = dfn.copy()
            df_show["Date"] = df_show["Date"].dt.strftime("%d.%m.%Y")
            st.dataframe(df_show, use_container_width=True)

        ts = time.strftime("%d.%m.%Y %H:%M")
        st.caption(f"Sist oppdatert: {ts}")

st.markdown('</div></div>', unsafe_allow_html=True)
