from pathlib import Path

import altair as alt
import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import (
    ALL_SEGMENTS,
    add_period_share,
    add_period_variation,
    aggregate_sales,
    filter_options,
    growth_contribution,
    load_data,
    market_map,
    previous_year_label,
    rank_by_period,
    seasonality,
    series_by_period,
    share_by_period,
    summary_table,
    top_series,
    with_series,
    year_over_year,
)


APP_DIR = Path(__file__).resolve().parent
MONTH_LABELS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
POSITIVE, NEGATIVE = "#16a34a", "#dc2626"

st.set_page_config(
    page_title="Emplacamentos Fenabrave",
    page_icon="🚗",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
    /* Sem cor fixa: no tema escuro um fundo claro deixava o texto branco ilegível. */
    [data-testid="stMetric"] {border:1px solid rgba(128,128,128,.35); padding:14px; border-radius:12px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def get_data(signature):
    """`signature` muda quando algum CSV muda, invalidando o cache."""
    return load_data(APP_DIR / "data")


def data_signature():
    return tuple(sorted((path.name, path.stat().st_mtime_ns) for path in (APP_DIR / "data").glob("*.csv")))


def thousands(value) -> str:
    return "—" if pd.isna(value) else f"{value:,.0f}".replace(",", ".")


def signed_percent(value) -> str:
    return "—" if pd.isna(value) else f"{value:+.1%}".replace(".", ",")


models_df, brands_df = get_data(data_signature())
minimum = models_df["competencia"].min().date()
maximum = models_df["competencia"].max().date()

st.title("Emplacamentos de veículos — Fenabrave")
st.caption("Automóveis e comerciais leves • janeiro/2021 a agosto/2026")

with st.sidebar:
    st.header("Filtros")
    date_range = st.date_input(
        "Período",
        value=(minimum, maximum),
        min_value=minimum,
        max_value=maximum,
        format="DD/MM/YYYY",
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range[0]

    period = st.radio("Agrupar período por", ["Ano", "Trimestre", "Mês"], horizontal=True)
    details = st.multiselect(
        "Detalhar por", ["Marca", "Modelo", "Tipo", "Categoria"], default=["Marca"]
    )
    measure = st.radio(
        "Exibir valores como",
        ["Números", "Percentual"],
        horizontal=True,
        help="Percentual mostra a participação dentro de cada período, o que neutraliza a sazonalidade.",
    )
    segments = st.multiselect("Segmento", list(ALL_SEGMENTS), default=list(ALL_SEGMENTS))

    all_categories = sorted(models_df.loc[models_df["segmento"].isin(segments), "categoria"].unique())
    selected_categories = st.multiselect(
        "Carroceria", all_categories, placeholder="Todas as carrocerias"
    )

    all_brands = sorted(set(models_df["marca"]) | set(brands_df["marca"]))
    selected_brands = st.multiselect("Marca", all_brands, placeholder="Todas as marcas")

    available_models = filter_options(
        models_df,
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
        segments,
        selected_brands,
        selected_categories,
    )
    selected_models = st.multiselect("Modelo", available_models, placeholder="Todos os modelos")

start = pd.Timestamp(start_date).to_period("M").to_timestamp()
end = pd.Timestamp(end_date).to_period("M").to_timestamp()


def aggregate(group_period: str, group_details: list[str]):
    return aggregate_sales(
        models=models_df,
        brands=brands_df,
        start=start,
        end=end,
        period=group_period,
        details=group_details,
        selected_segments=segments,
        selected_brands=selected_brands,
        selected_models=selected_models,
        selected_categories=selected_categories,
    )


result, source = aggregate(period, details)
result_with_variation = add_period_variation(result)
percent = measure == "Percentual"

# Toda comparação anual parte do mensal: assim jan-ago/2026 é medido contra jan-ago/2025,
# e não contra 2025 inteiro.
monthly_detail, _ = aggregate("Mês", details)
monthly_total, _ = aggregate("Mês", [])
annual = year_over_year(monthly_total, period)

period_totals = result.groupby("Periodo", as_index=False)["Emplacamentos"].sum()
total = int(result["Emplacamentos"].sum()) if not result.empty else 0
latest_value = int(period_totals["Emplacamentos"].iloc[-1]) if not period_totals.empty else 0
latest_period = period_totals["Periodo"].iloc[-1] if not period_totals.empty else "—"
latest_row = annual[annual["Periodo"] == latest_period]
latest_yoy = latest_row["Variacao_anual_percentual"].iloc[0] if not latest_row.empty else None
latest_months = int(latest_row["Meses"].iloc[0]) if not latest_row.empty else 0
expected_months = {"Ano": 12, "Trimestre": 3, "Mês": 1}[period]
partial = latest_months < expected_months
previous_value = (
    int(period_totals["Emplacamentos"].iloc[-2]) if len(period_totals) > 1 else None
)
sequential_delta = (latest_value / previous_value - 1) if previous_value else None

leading_category = "—"
if source == "modelos" or not selected_categories:
    by_category, _ = aggregate(period, ["Categoria"])
    if not by_category.empty:
        totals_by_category = by_category.groupby("Categoria")["Emplacamentos"].sum()
        leading_category = f"{totals_by_category.idxmax()}"
else:
    by_category = result.iloc[0:0]

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    f"Último {period.lower()} ({latest_period})",
    thousands(latest_value),
    delta=None if latest_yoy is None or pd.isna(latest_yoy) else signed_percent(latest_yoy),
    help="Variação contra os mesmos meses do ano anterior.",
)
col2.metric(
    "Vs. período anterior",
    "—" if partial or sequential_delta is None else signed_percent(sequential_delta),
    help=(
        f"{latest_period} tem {latest_months} de {expected_months} meses; comparar com um período "
        "completo daria uma queda que não existe. Use a variação anual do card ao lado."
        if partial
        else "Comparação com o período imediatamente anterior — sofre efeito de sazonalidade."
    ),
)
col3.metric("Total do intervalo", thousands(total))
brand_count = len(selected_brands) or (
    brands_df["marca"].nunique() if source == "marcas" else models_df["marca"].nunique()
)
if source == "modelos":
    model_count = len(selected_models) or models_df["modelo"].nunique()
    col4.metric("Marcas / modelos", f"{brand_count} / {model_count}")
else:
    col4.metric("Marcas", brand_count, help="Ranking de marcas da Fenabrave; sem quebra por modelo.")

if leading_category != "—":
    st.caption(f"Carroceria líder do recorte: **{leading_category}**.")

if partial:
    st.caption(
        f"⚠️ {latest_period} está incompleto ({latest_months} de {expected_months} meses). "
        "As comparações anuais usam apenas os meses disponíveis nos dois anos."
    )

if source == "modelos":
    st.info(
        "O cálculo usa o ranking público mensal de modelos da Fenabrave: até 50 automóveis e 50 comerciais leves. "
        "Modelos fora do ranking não entram na soma.",
        icon="ℹ️",
    )
else:
    st.caption("O cálculo usa o ranking mensal das 21 marcas publicado pela Fenabrave para automóveis + comerciais leves.")

if result.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
    st.stop()

st.subheader("Análises")
series_result = with_series(result)
highlighted = top_series(result, 12)
series_count = series_result["Série"].nunique()

(
    tab_evolution,
    tab_ranking,
    tab_map,
    tab_share,
    tab_momentum,
    tab_mix,
    tab_season,
) = st.tabs(
    ["Evolução", "Ranking", "Mapa do mercado", "Participação", "Momentum",
     "Mix de carroceria", "Sazonalidade"]
)

with tab_evolution:
    if percent:
        lines = (
            add_period_share(series_by_period(result))
            .pivot_table(index="Periodo", columns="Série", values="Participacao", aggfunc="sum", fill_value=0)
            .mul(100)
        )
        lines = lines[[column for column in lines.columns if column in highlighted]].sort_index()
        st.line_chart(lines, height=420, y_label="% do período")
        st.caption("Participação de cada série no total do período — sem efeito de sazonalidade.")
    else:
        smooth = period == "Mês" and st.checkbox(
            "Média móvel de 12 meses", help="Suaviza a sazonalidade sem sair de valores absolutos."
        )
        cumulative = (not smooth) and st.checkbox("Acumular ao longo do período")
        lines = (
            series_result[series_result["Série"].isin(highlighted)]
            .pivot_table(index="Periodo", columns="Série", values="Emplacamentos", aggfunc="sum", fill_value=0)
            .sort_index()
        )
        if smooth:
            lines = lines.rolling(12).mean().dropna(how="all")
            st.line_chart(lines, height=420, y_label="Média móvel 12m")
        else:
            st.line_chart(lines.cumsum() if cumulative else lines, height=420)
    if series_count > len(highlighted):
        st.caption(f"Exibindo as {len(highlighted)} maiores séries de {series_count}.")

with tab_ranking:
    ranking_limit = st.slider("Itens no ranking", 5, 30, 15)
    ranking = (
        series_result.groupby("Série", as_index=False)["Emplacamentos"]
        .sum()
        .nlargest(ranking_limit, "Emplacamentos")
    )
    if percent:
        ranking["Participação (%)"] = (
            ranking["Emplacamentos"] / series_result["Emplacamentos"].sum() * 100
        )
    st.bar_chart(
        ranking,
        x="Série",
        y="Participação (%)" if percent else "Emplacamentos",
        horizontal=True,
        height=max(320, 28 * len(ranking)),
    )

    st.markdown("**Placar do período**")
    summary = summary_table(monthly_detail, period, ranking_limit)
    summary["Participação"] = summary["Participação"] * 100
    summary["Variação anual %"] = summary["Variação anual %"] * 100
    st.dataframe(
        summary,
        hide_index=True,
        width="stretch",
        column_config={
            "Série": st.column_config.TextColumn("Série", width="medium"),
            "Histórico": st.column_config.LineChartColumn(
                "Histórico", y_min=0, help="Evolução dentro do intervalo filtrado."
            ),
            "Total": st.column_config.NumberColumn("Total", format="%d"),
            "Participação": st.column_config.ProgressColumn(
                "Participação", format="%.1f%%", min_value=0.0, max_value=float(max(summary["Participação"].max(), 1))
            ),
            "Último período": st.column_config.NumberColumn(f"Último {period.lower()}", format="%d"),
            "Variação anual": st.column_config.NumberColumn("Δ anual", format="%+d"),
            "Variação anual %": st.column_config.NumberColumn("Δ anual %", format="%+.1f%%"),
            "Participação (p.p.)": st.column_config.NumberColumn("Δ participação", format="%+.2f p.p."),
        },
    )
    st.caption(
        f"Δ anual compara os {latest_months} mês(es) de {latest_period} com os mesmos meses de "
        f"{previous_year_label(latest_period)}. "
        "Δ participação mostra ganho ou perda de mercado em pontos percentuais."
    )

    st.markdown("**Evolução de posição**")
    positions = rank_by_period(result)
    positions = positions[positions["Série"].isin(top_series(result, 10))]
    st.altair_chart(
        alt.Chart(positions)
        .mark_line(point=True)
        .encode(
            x=alt.X("Periodo:O", title=period),
            y=alt.Y("Posicao:Q", scale=alt.Scale(reverse=True), title="Posição no ranking"),
            color=alt.Color("Série:N", title=None),
            tooltip=[
                alt.Tooltip("Periodo:O", title=period),
                alt.Tooltip("Série:N"),
                alt.Tooltip("Posicao:Q", title="Posição"),
                alt.Tooltip("Emplacamentos:Q", format=",.0f"),
            ],
        )
        .properties(height=380)
    )

with tab_map:
    levels = st.multiselect(
        "Hierarquia do mapa",
        ["Tipo", "Categoria", "Marca", "Modelo"],
        default=["Marca", "Modelo"],
        help="Cada nível vira um bloco aninhado. Clique num bloco para entrar nele.",
    )
    if not levels:
        st.info("Escolha ao menos um nível para montar o mapa.", icon="ℹ️")
    else:
        tree, _ = aggregate("Mês", levels)
        blocks = market_map(tree, period)
        if blocks.empty:
            st.warning("Nenhum dado para o recorte selecionado.")
        else:
            figure = px.treemap(
                blocks,
                path=[px.Constant("Mercado")] + levels,
                values="Emplacamentos",
                color="Variacao_anual_percentual",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                range_color=(-0.5, 0.5),
            )
            figure.update_traces(
                texttemplate="<b>%{label}</b><br>%{value:,.0f}<br>%{percentRoot:.1%}",
                hovertemplate=(
                    "<b>%{label}</b><br>Emplacamentos: %{value:,.0f}"
                    "<br>Participação: %{percentRoot:.1%} do mapa"
                    "<br>Δ anual: %{color:+.1%}<extra></extra>"
                ),
                marker_line_width=1,
                marker_line_color="white",
            )
            figure.update_layout(
                uniformtext=dict(minsize=9, mode="hide"),
                margin=dict(t=24, l=0, r=0, b=0),
                height=560,
                separators=",.",
                coloraxis_colorbar=dict(title="Δ anual", tickformat="+.0%"),
            )
            st.plotly_chart(figure, width="stretch")
            st.caption(
                f"Tamanho do bloco = volume no intervalo. Cor = variação de {latest_period} contra os "
                f"mesmos meses de {previous_year_label(latest_period)} — verde cresce, vermelho cai, "
                "cinza sem base de comparação."
            )

with tab_share:
    if series_count == 1:
        st.info("Selecione um detalhamento por marca, modelo, tipo ou categoria para comparar participações.", icon="ℹ️")
    else:
        share = share_by_period(result, 10)
        st.altair_chart(
            alt.Chart(share)
            .mark_area()
            .encode(
                x=alt.X("Periodo:O", title=period),
                y=alt.Y(
                    "Participacao:Q" if percent else "Emplacamentos:Q",
                    stack="normalize" if percent else True,
                    title="Participação" if percent else "Emplacamentos",
                    axis=alt.Axis(format="%" if percent else ",.0f"),
                ),
                color=alt.Color("Série:N", title=None),
                tooltip=[
                    alt.Tooltip("Periodo:O", title=period),
                    alt.Tooltip("Série:N"),
                    alt.Tooltip("Emplacamentos:Q", format=",.0f"),
                    alt.Tooltip("Participacao:Q", title="Participação", format=".1%"),
                ],
            )
            .properties(height=420)
        )
        st.caption("Séries fora das 10 maiores aparecem agrupadas em “Outros”.")

with tab_momentum:
    st.markdown("**Mercado do recorte, ano contra ano**")
    market = annual.dropna(subset=["Variacao_anual_percentual"])
    if market.empty:
        st.info("São necessários 12 meses de histórico para comparar ano contra ano.", icon="ℹ️")
    else:
        st.altair_chart(
            alt.Chart(market)
            .mark_bar()
            .encode(
                x=alt.X("Periodo:O", title=period),
                y=alt.Y(
                    "Variacao_anual_percentual:Q",
                    title="Variação vs. mesmo período do ano anterior",
                    axis=alt.Axis(format="%"),
                ),
                color=alt.condition(
                    alt.datum.Variacao_anual_percentual >= 0, alt.value(POSITIVE), alt.value(NEGATIVE)
                ),
                tooltip=[
                    alt.Tooltip("Periodo:O", title=period),
                    alt.Tooltip("Emplacamentos:Q", format=",.0f"),
                    alt.Tooltip("Emplacamentos_anterior:Q", title="Ano anterior", format=",.0f"),
                    alt.Tooltip("Variacao_anual_percentual:Q", title="Δ anual", format="+.1%"),
                ],
            )
            .properties(height=320)
        )

    st.markdown(f"**Quem moveu o mercado em {latest_period}**")
    contribution = growth_contribution(monthly_detail, period, 15)
    if contribution.empty:
        st.info("Sem base do ano anterior para comparar as séries.", icon="ℹ️")
    else:
        st.altair_chart(
            alt.Chart(contribution)
            .mark_bar()
            .encode(
                x=alt.X("Variacao_anual:Q", title="Emplacamentos ganhos ou perdidos vs. ano anterior"),
                y=alt.Y("Série:N", title=None, sort="-x"),
                color=alt.condition(
                    alt.datum.Variacao_anual >= 0, alt.value(POSITIVE), alt.value(NEGATIVE)
                ),
                tooltip=[
                    alt.Tooltip("Série:N"),
                    alt.Tooltip("Emplacamentos:Q", format=",.0f"),
                    alt.Tooltip("Emplacamentos_anterior:Q", title="Ano anterior", format=",.0f"),
                    alt.Tooltip("Variacao_anual:Q", title="Δ absoluto", format="+,.0f"),
                    alt.Tooltip("Variacao_anual_percentual:Q", title="Δ %", format="+.1%"),
                ],
            )
            .properties(height=max(300, 28 * len(contribution)))
        )
        st.caption("Contribuição absoluta de cada série para o crescimento (ou queda) do último período.")

    st.markdown("**Tamanho x crescimento**")
    quadrant = (
        summary_table(monthly_detail, period, 25)
        .dropna(subset=["Variação anual %"])
        .rename(columns={"Variação anual %": "Crescimento", "Participação (p.p.)": "Delta"})
    )
    if quadrant.empty:
        st.info("Sem histórico suficiente para o comparativo.", icon="ℹ️")
    else:
        points = (
            alt.Chart(quadrant)
            .mark_circle(opacity=0.75)
            .encode(
                x=alt.X("Total:Q", title="Volume no intervalo", scale=alt.Scale(type="sqrt")),
                y=alt.Y("Crescimento:Q", title="Δ anual", axis=alt.Axis(format="%")),
                size=alt.Size("Total:Q", legend=None),
                color=alt.condition(alt.datum.Crescimento >= 0, alt.value(POSITIVE), alt.value(NEGATIVE)),
                tooltip=[
                    alt.Tooltip("Série:N"),
                    alt.Tooltip("Total:Q", format=",.0f"),
                    alt.Tooltip("Crescimento:Q", title="Δ anual", format="+.1%"),
                    alt.Tooltip("Delta:Q", title="Δ participação (p.p.)", format="+.2f"),
                ],
            )
        )
        zero = (
            alt.Chart(pd.DataFrame({"Crescimento": [0.0]}))
            .mark_rule(strokeDash=[4, 4], color="#94a3b8")
            .encode(y="Crescimento:Q")
        )
        st.altair_chart((points + zero).properties(height=420))
        median_growth = float(quadrant["Crescimento"].median())
        st.caption(
            "Bolhas acima da linha crescem contra o ano anterior; à direita, as maiores em volume. "
            f"Mediana do recorte: {median_growth:+.1%}"
        )

with tab_mix:
    mix, _ = aggregate(period, ["Categoria"])
    if mix.empty:
        st.info("Sem dados de carroceria para o recorte.", icon="ℹ️")
    else:
        mix_share = add_period_share(mix)
        st.altair_chart(
            alt.Chart(mix_share)
            .mark_area()
            .encode(
                x=alt.X("Periodo:O", title=period),
                y=alt.Y(
                    "Participacao:Q" if percent else "Emplacamentos:Q",
                    stack="normalize" if percent else True,
                    title="Participação" if percent else "Emplacamentos",
                    axis=alt.Axis(format="%" if percent else ",.0f"),
                ),
                color=alt.Color("Categoria:N", title=None),
                tooltip=[
                    alt.Tooltip("Periodo:O", title=period),
                    alt.Tooltip("Categoria:N"),
                    alt.Tooltip("Emplacamentos:Q", format=",.0f"),
                    alt.Tooltip("Participacao:Q", title="Participação", format=".1%"),
                ],
            )
            .properties(height=400)
        )
        monthly_mix, _ = aggregate("Mês", ["Categoria"])
        mix_summary = summary_table(monthly_mix, period, 20)
        mix_summary["Participação"] = mix_summary["Participação"] * 100
        mix_summary["Variação anual %"] = mix_summary["Variação anual %"] * 100
        st.dataframe(
            mix_summary,
            hide_index=True,
            width="stretch",
            column_config={
                "Série": st.column_config.TextColumn("Carroceria", width="medium"),
                "Histórico": st.column_config.LineChartColumn("Histórico", y_min=0),
                "Total": st.column_config.NumberColumn("Total", format="%d"),
                "Participação": st.column_config.ProgressColumn(
                    "Participação", format="%.1f%%", min_value=0.0,
                    max_value=float(max(mix_summary["Participação"].max(), 1)),
                ),
                "Último período": st.column_config.NumberColumn(f"Último {period.lower()}", format="%d"),
                "Variação anual": st.column_config.NumberColumn("Δ anual", format="%+d"),
                "Variação anual %": st.column_config.NumberColumn("Δ anual %", format="%+.1f%%"),
                "Participação (p.p.)": st.column_config.NumberColumn("Δ participação", format="%+.2f p.p."),
            },
        )
        st.caption(
            "Carroceria vem de uma tabela de apoio (data/carrocerias.csv) que classifica cada modelo "
            "do ranking Fenabrave em hatch, sedã, SUV, minivan, picape, furgão, chassi leve e off-road, por porte."
        )

with tab_season:
    season = seasonality(monthly_total)
    season["Mês"] = season["Mes"].map(lambda month: MONTH_LABELS[month - 1])
    if percent:
        yearly = season.groupby("Ano")["Emplacamentos"].transform("sum")
        season["Valor"] = season["Emplacamentos"].div(yearly.where(yearly.ne(0))).mul(100)
    else:
        season["Valor"] = season["Emplacamentos"]
    st.altair_chart(
        alt.Chart(season)
        .mark_rect()
        .encode(
            x=alt.X("Mês:O", title="Mês", sort=MONTH_LABELS),
            y=alt.Y("Ano:O", title="Ano"),
            color=alt.Color(
                "Valor:Q",
                scale=alt.Scale(scheme="blues"),
                title="% do ano" if percent else "Emplacamentos",
                legend=alt.Legend(format=".1f" if percent else ",.0f"),
            ),
            tooltip=[
                alt.Tooltip("Ano:O"),
                alt.Tooltip("Mês:O"),
                alt.Tooltip("Emplacamentos:Q", format=",.0f"),
                alt.Tooltip("Valor:Q", title="% do ano", format=".1f"),
            ],
        )
        .properties(height=max(240, 34 * season["Ano"].nunique()))
    )
    st.caption(
        "Peso de cada mês dentro do próprio ano, em % — evidencia o padrão sazonal."
        if percent
        else "Volume mensal do recorte, sempre por mês — independente do agrupamento escolhido."
    )

st.subheader("Dados agrupados")
table_source = add_period_share(result_with_variation) if percent else result_with_variation
display = table_source.rename(
    columns={
        "Periodo": period,
        "Variacao": "Variação",
        "Variacao_percentual": "Variação %",
        "Tendencia": "Tendência",
        "Participacao": "Participação",
    }
)


def color_trend(row):
    variation = row.get("Variação")
    if pd.isna(variation):
        return ["background-color: #f8fafc; color: #475569"] * len(row)
    if variation > 0:
        return ["background-color: #dcfce7; color: #166534"] * len(row)
    if variation < 0:
        return ["background-color: #fee2e2; color: #991b1b"] * len(row)
    return ["background-color: #fef3c7; color: #92400e"] * len(row)


styled_display = (
    display.style
    .apply(color_trend, axis=1)
    .format({
        "Emplacamentos": thousands,
        "Variação": thousands,
        "Variação %": signed_percent,
        "Participação": lambda value: "—" if pd.isna(value) else f"{value:.1%}".replace(".", ","),
    })
)
st.dataframe(styled_display, width="stretch", hide_index=True)

csv_bytes = display.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "Baixar resultado em CSV",
    data=csv_bytes,
    file_name="emplacamentos_fenabrave_agrupados.csv",
    mime="text/csv",
)

with st.expander("Sobre os dados"):
    st.write(
        "Os valores representam emplacamentos de veículos novos, usados como aproximação das vendas. "
        "A origem é o Informativo de Emplacamentos da Fenabrave; não são notas fiscais de venda."
    )
    st.link_button(
        "Abrir fonte oficial",
        "https://www.fenabrave.org.br/portalv2/Conteudo/emplacamentos",
    )
