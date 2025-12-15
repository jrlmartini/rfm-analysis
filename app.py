import io
import math
from datetime import datetime
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

st.set_page_config(page_title="Análise RFM", layout="wide")

TITLE = "Análise RFM"
st.title(TITLE)

COLOR_MAP = {
    "Campeões": "#264653",
    "Fiel": "#2a9d8f",
    "Atencao": "#e76f51",
    "Quase Domententes": "#f4a261",
    "Promessas": "#e9c46a",
    "Novos Clientes": "#f4d35e",
    "Hibernando": "#8d99ae",
    "Nao Pode Perder": "#d62828",
    "Em Risco": "#bc4749",
    "Perdidos": "#6d597a",
    "Fiel em Potencial": "#ffb703",
    "Sem Categoria": "#e0e0e0",
}

CATEGORY_ORDER = list(COLOR_MAP.keys())


def classificar(score_r: int, score_fm: int) -> str:
    if score_r == 5 and score_fm == 5:
        return "Campeões"
    if (score_r == 5 and score_fm == 4) or (score_r == 4 and score_fm in {4, 5}) or (score_r == 3 and score_fm in {4, 5}):
        return "Fiel"
    if score_r == 3 and score_fm == 3:
        return "Atencao"
    if score_r == 3 and score_fm in {1, 2}:
        return "Quase Domententes"
    if score_r == 4 and score_fm == 1:
        return "Promessas"
    if score_r == 5 and score_fm == 1:
        return "Novos Clientes"
    if score_r == 2 and score_fm == 2:
        return "Hibernando"
    if score_r in {1, 2} and score_fm == 5:
        return "Nao Pode Perder"
    if score_r in {1, 2} and score_fm in {3, 4}:
        return "Em Risco"
    if (score_r == 1 and score_fm in {1, 2}) or (score_r == 2 and score_fm == 1):
        return "Perdidos"
    if score_r in {4, 5} and score_fm in {2, 3}:
        return "Fiel em Potencial"
    return "Sem Categoria"


def quintile_score_from_percentile(series: pd.Series, labels):
    percentiles = series.rank(pct=True, method="average")
    bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
    return pd.cut(percentiles, bins=bins, labels=labels, include_lowest=True, duplicates="drop").astype(int)


st.sidebar.header("Controles")
upload_file = st.sidebar.file_uploader("Upload do Excel", type=["xlsx"])
prazo_meses = st.sidebar.slider("Prazo (meses)", min_value=1, max_value=36, value=12, step=1)
segmentos_selecionados = st.sidebar.multiselect(
    "Segmento",
    options=["Autarquia", "Privado"],
    default=["Autarquia", "Privado"],
)

iniciar = st.sidebar.button("Iniciar Análise RFM")


@st.cache_data(show_spinner=False)
def carregar_planilha(file) -> pd.DataFrame:
    return pd.read_excel(file)


if iniciar:
    if not upload_file:
        st.warning("⚠️ Por favor, envie um arquivo Excel.")
    else:
        try:
            df_raw = carregar_planilha(upload_file)
        except Exception:
            df_raw = pd.DataFrame()

        if df_raw.empty:
            st.warning("⚠️ Arquivo vazio.")
        else:
            df = df_raw.copy()
            data_col = "Data de Emissão (completa)"
            valor_col = "Total da Nota Fiscal"
            cliente_col = "Cliente (Nome Fantasia)"

            df[data_col] = pd.to_datetime(df[data_col], errors="coerce")
            df[valor_col] = pd.to_numeric(df[valor_col], errors="coerce")
            df["Tags"] = df.get("Tags", "").astype(str)

            if segmentos_selecionados:
                pattern = "|".join(segmentos_selecionados)
                df = df[df["Tags"].str.contains(pattern, case=False, na=False)]

            df = df[[cliente_col, data_col, valor_col]].dropna()

            limite_data = pd.Timestamp(datetime.now()) - pd.DateOffset(months=prazo_meses)
            df_filtrado = df[df[data_col] >= limite_data]

            if df_filtrado.empty:
                st.warning("⚠️ Sem movimentação no período selecionado.")
            else:
                latest_date = df_filtrado[data_col].max()

                recency = df_filtrado.groupby(cliente_col)[data_col].max().apply(lambda d: (latest_date - d).days)
                frequency = df_filtrado.groupby(cliente_col)[data_col].count()
                monetary = df_filtrado.groupby(cliente_col)[valor_col].sum()

                rfm = pd.DataFrame({
                    "Cliente": recency.index,
                    "Recency": recency.values,
                    "Frequency": frequency.values,
                    "Monetary": monetary.values,
                })

                rfm["Score_R"] = quintile_score_from_percentile(rfm["Recency"], labels=[5, 4, 3, 2, 1])

                freq_rank = rfm["Frequency"].rank(method="average")
                rfm["Score_F"] = quintile_score_from_percentile(freq_rank, labels=[1, 2, 3, 4, 5])

                mon_rank = rfm["Monetary"].rank(method="average")
                rfm["Score_M"] = quintile_score_from_percentile(mon_rank, labels=[1, 2, 3, 4, 5])

                rfm["Score_FM"] = ((rfm["Score_F"] + rfm["Score_M"]) / 2).round().astype(int)
                rfm["Category"] = rfm.apply(lambda row: classificar(row["Score_R"], row["Score_FM"]), axis=1)

                st.success("Análise concluída com sucesso!")

                rfm_heatmap_path = Path("rfm_heatmap.png")
                rfm_barras_path = Path("rfm_barras.png")

                # Heatmap preparation
                grade = pd.DataFrame(list(product(range(1, 6), repeat=2)), columns=["Score_FM", "Score_R"])
                grade["CategoriaCelula"] = grade.apply(lambda row: classificar(row["Score_R"], row["Score_FM"]), axis=1)

                counts = rfm.groupby(["Score_FM", "Score_R"]).size().reset_index(name="Count")
                heatmap_full = grade.merge(counts, on=["Score_FM", "Score_R"], how="left").fillna({"Count": 0})

                pivot_cat = heatmap_full.pivot(index="Score_FM", columns="Score_R", values="CategoriaCelula")
                pivot_count = heatmap_full.pivot(index="Score_FM", columns="Score_R", values="Count").fillna(0)

                category_to_idx = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
                numeric_matrix = pivot_cat.applymap(lambda c: category_to_idx.get(c, category_to_idx["Sem Categoria"]))

                annot = pivot_count.copy().astype(int).astype(str) + "\n" + pivot_cat.fillna("Sem Categoria")

                plt.close("all")
                fig, ax = plt.subplots(figsize=(10, 8))
                cmap = sns.color_palette(list(COLOR_MAP.values()), n_colors=len(COLOR_MAP))
                sns.heatmap(
                    numeric_matrix,
                    cmap=cmap,
                    cbar=False,
                    annot=annot,
                    fmt="",
                    linewidths=0.5,
                    linecolor="white",
                    ax=ax,
                )
                ax.invert_yaxis()
                ax.set_title("Análise RFM - Heatmap de Categorias (Completo)")
                ax.set_xlabel("Recência (Score_R 1→5)")
                ax.set_ylabel("Frequência + Monetário (Score_FM 1→5)")
                ax.set_xticklabels(range(1, 6))
                ax.set_yticklabels(range(1, 6))
                fig.tight_layout()
                fig.savefig(rfm_heatmap_path, dpi=150)
                st.pyplot(fig)
                st.info(f"📊 Heatmap salvo em {rfm_heatmap_path.name}")

                # Bar chart
                cat_counts = rfm["Category"].value_counts().reindex(CATEGORY_ORDER, fill_value=0)
                fig_bar, ax_bar = plt.subplots(figsize=(10, 5))
                ax_bar.bar(cat_counts.index, cat_counts.values, color=[COLOR_MAP[c] for c in cat_counts.index])
                ax_bar.set_title("Clientes por Categoria RFM")
                ax_bar.set_ylabel("Número de Clientes")
                ax_bar.tick_params(axis="x", rotation=45)
                fig_bar.tight_layout()
                fig_bar.savefig(rfm_barras_path, dpi=150)
                st.pyplot(fig_bar)
                st.info(f"📈 Barras salvas em {rfm_barras_path.name}")

                # Tabela com filtro por categoria
                categorias_disponiveis = ["Todas"] + [c for c in CATEGORY_ORDER if c in rfm["Category"].unique()]
                categoria_selecionada = st.selectbox("Filtrar por Categoria", categorias_disponiveis)
                if categoria_selecionada != "Todas":
                    rfm_view = rfm[rfm["Category"] == categoria_selecionada]
                else:
                    rfm_view = rfm.copy()

                st.dataframe(
                    rfm_view[
                        [
                            "Cliente",
                            "Recency",
                            "Frequency",
                            "Monetary",
                            "Score_R",
                            "Score_F",
                            "Score_M",
                            "Score_FM",
                            "Category",
                        ]
                    ].sort_values(["Category", "Cliente"]),
                    use_container_width=True,
                )

                # Excel export
                resumo_categorias = cat_counts.reset_index()
                resumo_categorias.columns = ["Categoria", "Qtd Clientes"]

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    rfm.to_excel(writer, sheet_name="Clientes RFM", index=False)
                    resumo_categorias.to_excel(writer, sheet_name="Resumo Categorias", index=False)
                excel_bytes = output.getvalue()

                resultado_path = Path("rfm_resultado.xlsx")
                with open(resultado_path, "wb") as f:
                    f.write(excel_bytes)

                st.success(
                    "📁 Planilha gerada: rfm_resultado.xlsx",
                )
                st.download_button(
                    label="Baixar rfm_resultado.xlsx",
                    data=excel_bytes,
                    file_name="rfm_resultado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
else:
    st.info("Envie o arquivo Excel, ajuste os filtros e clique em 'Iniciar Análise RFM'.")
