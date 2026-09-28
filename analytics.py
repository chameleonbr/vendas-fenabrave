from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


ALL_SEGMENTS = ("Automóveis", "Comerciais leves")

# Detail dimensions, in the order they are displayed and grouped.
DETAIL_COLUMNS = {"Tipo": "tipo", "Categoria": "categoria", "Marca": "marca", "Modelo": "modelo"}
SERIES_COLUMNS = tuple(DETAIL_COLUMNS) + ("Série",)
UNCLASSIFIED = "Não classificado"


def load_data(data_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    data_dir = Path(data_dir)
    models = pd.read_csv(data_dir / "modelos.csv", encoding="utf-8-sig")
    brands = pd.read_csv(data_dir / "marcas.csv", encoding="utf-8-sig")
    bodies = pd.read_csv(data_dir / "carrocerias.csv", encoding="utf-8-sig")

    for frame in (models, brands):
        frame["competencia"] = pd.to_datetime(frame["competencia"], format="%Y-%m")
        frame["quantidade"] = pd.to_numeric(frame["quantidade"], errors="raise").astype("int64")
    brands["participacao"] = pd.to_numeric(brands["participacao"], errors="raise")

    models = models.merge(bodies, on=["segmento", "marca", "modelo"], how="left")
    models[["tipo", "categoria"]] = models[["tipo", "categoria"]].fillna(UNCLASSIFIED)
    return models, brands


def _period_column(frame: pd.DataFrame, period: str) -> pd.Series:
    dates = frame["competencia"]
    if period == "Ano":
        return dates.dt.year.astype(str)
    if period == "Trimestre":
        return dates.dt.year.astype(str) + " T" + dates.dt.quarter.astype(str)
    return dates.dt.strftime("%Y-%m")


def aggregate_sales(
    models: pd.DataFrame,
    brands: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    period: str,
    details: Iterable[str],
    selected_segments: Iterable[str] = ALL_SEGMENTS,
    selected_brands: Iterable[str] = (),
    selected_models: Iterable[str] = (),
    selected_categories: Iterable[str] = (),
) -> tuple[pd.DataFrame, str]:
    details = list(details)
    selected_segments = list(selected_segments)
    selected_brands = list(selected_brands)
    selected_models = list(selected_models)
    selected_categories = list(selected_categories)

    needs_model_base = (
        bool({"Modelo", "Tipo", "Categoria"} & set(details))
        or bool(selected_models)
        or bool(selected_categories)
        or set(selected_segments) != set(ALL_SEGMENTS)
    )

    if needs_model_base:
        frame = models.copy()
        source = "modelos"
        if selected_segments:
            frame = frame[frame["segmento"].isin(selected_segments)]
        else:
            frame = frame.iloc[0:0]
        if selected_models:
            frame = frame[frame["modelo"].isin(selected_models)]
        if selected_categories:
            frame = frame[frame["categoria"].isin(selected_categories)]
    else:
        frame = brands.copy()
        source = "marcas"

    frame = frame[(frame["competencia"] >= start) & (frame["competencia"] <= end)]
    if selected_brands:
        frame = frame[frame["marca"].isin(selected_brands)]

    frame = frame.assign(Periodo=_period_column(frame, period))
    group_columns = ["Periodo"] + [
        column for label, column in DETAIL_COLUMNS.items() if label in details
    ]

    result = (
        frame.groupby(group_columns, as_index=False, observed=True)["quantidade"]
        .sum()
        .sort_values(group_columns, kind="stable")
        .rename(columns={**{v: k for k, v in DETAIL_COLUMNS.items()}, "quantidade": "Emplacamentos"})
        .reset_index(drop=True)
    )
    return result, source


def detail_columns(result: pd.DataFrame) -> list[str]:
    """Detail columns present in a result, in display order."""
    return [column for column in SERIES_COLUMNS if column in result.columns]


def add_period_variation(result: pd.DataFrame) -> pd.DataFrame:
    """Compare each series with its immediately preceding displayed period."""
    if result.empty:
        return result.assign(Variacao=pd.Series(dtype="float64"),
                             Variacao_percentual=pd.Series(dtype="float64"),
                             Tendencia=pd.Series(dtype="object"))

    columns = detail_columns(result)
    compared = result.sort_values(columns + ["Periodo"], kind="stable").copy()

    if columns:
        previous = compared.groupby(columns, observed=True)["Emplacamentos"].shift(1)
    else:
        previous = compared["Emplacamentos"].shift(1)

    compared["Variacao"] = compared["Emplacamentos"] - previous
    compared["Variacao_percentual"] = compared["Variacao"].div(previous.where(previous.ne(0)))
    compared["Tendencia"] = "Sem comparação"
    compared.loc[compared["Variacao"] > 0, "Tendencia"] = "▲ Aumento"
    compared.loc[compared["Variacao"] < 0, "Tendencia"] = "▼ Queda"
    compared.loc[compared["Variacao"] == 0, "Tendencia"] = "● Estável"
    return compared.sort_values(["Periodo"] + columns, kind="stable").reset_index(drop=True)


def previous_year_label(label: str) -> str:
    """Label of the same period one year earlier ('2024-07' -> '2023-07')."""
    if "-" in label:
        year, month = label.split("-")
        return f"{int(year) - 1}-{month}"
    if " T" in label:
        year, quarter = label.split(" T")
        return f"{int(year) - 1} T{quarter}"
    return str(int(label) - 1)


def period_label(year_month: str, period: str) -> str:
    """Period label of a 'YYYY-MM' competence."""
    year, month = year_month.split("-")
    if period == "Ano":
        return year
    if period == "Trimestre":
        return f"{year} T{(int(month) - 1) // 3 + 1}"
    return year_month


def year_over_year(monthly: pd.DataFrame, period: str) -> pd.DataFrame:
    """Group monthly rows into periods and compare with the SAME months one year earlier.

    Comparing period labels alone would put a partial year (jan-ago) against a full one and
    invent a collapse, so the base is assembled month by month.
    """
    columns = detail_columns(monthly)
    if monthly.empty:
        return monthly.assign(Emplacamentos_anterior=pd.Series(dtype="float64"),
                              Variacao_anual=pd.Series(dtype="float64"),
                              Variacao_anual_percentual=pd.Series(dtype="float64"),
                              Meses=pd.Series(dtype="int64"))

    base = monthly[columns + ["Periodo", "Emplacamentos"]].rename(
        columns={"Emplacamentos": "Emplacamentos_anterior"}
    ).copy()
    base["Periodo"] = base["Periodo"].map(
        lambda label: f"{int(label.split('-')[0]) + 1}-{label.split('-')[1]}"
    )
    merged = monthly.merge(base, on=columns + ["Periodo"], how="left")
    merged["_rotulo"] = merged["Periodo"].map(lambda label: period_label(label, period))

    grouped = merged.groupby(columns + ["_rotulo"], as_index=False, observed=True).agg(
        Emplacamentos=("Emplacamentos", "sum"),
        Emplacamentos_anterior=("Emplacamentos_anterior", "sum"),
        Meses=("Periodo", "nunique"),
        Meses_comparaveis=("Emplacamentos_anterior", "count"),
    )
    # Sem nenhum mês de base não há comparação — soma zero não é queda de 100%.
    grouped["Emplacamentos_anterior"] = grouped["Emplacamentos_anterior"].where(
        grouped["Meses_comparaveis"] > 0
    )
    previous = grouped["Emplacamentos_anterior"]
    grouped["Variacao_anual"] = grouped["Emplacamentos"] - previous
    grouped["Variacao_anual_percentual"] = grouped["Variacao_anual"].div(previous.where(previous.ne(0)))
    return grouped.drop(columns="Meses_comparaveis").rename(columns={"_rotulo": "Periodo"})


def with_series(result: pd.DataFrame) -> pd.DataFrame:
    """Add a 'Série' label joining the detail columns ('Total' when there is none)."""
    columns = detail_columns(result)
    frame = result.copy()
    if "Série" in columns:
        return frame
    if columns:
        frame["Série"] = frame[columns].astype(str).agg(" / ".join, axis=1)
    else:
        frame["Série"] = "Total"
    return frame


def series_by_period(result: pd.DataFrame) -> pd.DataFrame:
    """Collapse a result to one row per 'Série' and period."""
    frame = with_series(result)
    return frame.groupby(["Série", "Periodo"], as_index=False, observed=True)["Emplacamentos"].sum()


def top_series(result: pd.DataFrame, limit: int = 12) -> list[str]:
    """Series names ordered by total volume, biggest first."""
    if result.empty:
        return []
    totals = with_series(result).groupby("Série", observed=True)["Emplacamentos"].sum()
    return totals.nlargest(limit).index.tolist()


def add_period_share(result: pd.DataFrame) -> pd.DataFrame:
    """Add 'Participacao': share of each row inside its own period (100% por período)."""
    frame = result.copy()
    totals = frame.groupby("Periodo", observed=True)["Emplacamentos"].transform("sum")
    frame["Participacao"] = frame["Emplacamentos"].div(totals.where(totals.ne(0)))
    return frame


def share_by_period(result: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    """Share of each series inside every period; series beyond `limit` become 'Outros'."""
    frame = with_series(result)
    kept = set(top_series(result, limit))
    frame["Série"] = frame["Série"].where(frame["Série"].isin(kept), "Outros")
    grouped = frame.groupby(["Periodo", "Série"], as_index=False, observed=True)["Emplacamentos"].sum()
    return add_period_share(grouped)


def seasonality(monthly: pd.DataFrame) -> pd.DataFrame:
    """Ano/mês table from a result grouped by 'Mês' (Periodo no formato YYYY-MM)."""
    frame = monthly.groupby("Periodo", as_index=False, observed=True)["Emplacamentos"].sum()
    if frame.empty:
        return frame.assign(Ano=pd.Series(dtype="object"), Mes=pd.Series(dtype="int64"))
    parts = frame["Periodo"].str.split("-", expand=True)
    frame["Ano"] = parts[0]
    frame["Mes"] = parts[1].astype("int64")
    return frame


def rank_by_period(result: pd.DataFrame) -> pd.DataFrame:
    """Position of each series inside each period (1 = biggest)."""
    frame = series_by_period(result)
    frame["Posicao"] = (
        frame.groupby("Periodo", observed=True)["Emplacamentos"]
        .rank(method="first", ascending=False)
        .astype("int64")
    )
    return frame


def growth_contribution(monthly: pd.DataFrame, period: str, limit: int = 15) -> pd.DataFrame:
    """Who moved the market: year-over-year change of each series in the latest period."""
    frame = series_by_period(monthly)
    if frame.empty:
        return frame.assign(Variacao_anual=pd.Series(dtype="float64"))
    compared = year_over_year(frame, period)
    latest = compared["Periodo"].max()
    compared = compared[compared["Periodo"] == latest].dropna(subset=["Variacao_anual"])
    return (
        compared.assign(Ordem=compared["Variacao_anual"].abs())
        .nlargest(limit, "Ordem")
        .drop(columns="Ordem")
        .reset_index(drop=True)
    )


def summary_table(monthly: pd.DataFrame, period: str, limit: int = 20) -> pd.DataFrame:
    """One row per series: sparkline history, total, share and year-over-year movement."""
    frame = series_by_period(monthly)
    if frame.empty:
        return pd.DataFrame(
            columns=["Série", "Histórico", "Total", "Participação", "Último período",
                     "Variação anual", "Variação anual %", "Participação (p.p.)"]
        )

    compared = year_over_year(frame, period)
    periods = sorted(compared["Periodo"].unique())
    latest = periods[-1]
    wide = (
        compared.pivot_table(index="Série", columns="Periodo", values="Emplacamentos",
                             aggfunc="sum", fill_value=0)
        .reindex(columns=periods, fill_value=0)
    )
    last_rows = compared[compared["Periodo"] == latest].set_index("Série")
    shares = add_period_share(compared).set_index(["Periodo", "Série"])["Participacao"]
    share_now = shares.loc[latest]
    # Participação do mesmo recorte de meses no ano anterior, para um Δ p.p. honesto.
    previous_totals = last_rows["Emplacamentos_anterior"]
    previous_market = previous_totals.sum()
    share_before = previous_totals / previous_market if previous_market else previous_totals * float("nan")

    totals = wide.sum(axis=1)
    summary = pd.DataFrame({
        "Série": wide.index,
        "Histórico": [row.tolist() for _, row in wide.iterrows()],
        "Total": totals.to_numpy(),
        "Participação": (totals / totals.sum()).to_numpy() if totals.sum() else 0.0,
    })
    summary["Último período"] = summary["Série"].map(last_rows["Emplacamentos"]).fillna(0)
    summary["Variação anual"] = summary["Série"].map(last_rows["Variacao_anual"])
    summary["Variação anual %"] = summary["Série"].map(last_rows["Variacao_anual_percentual"])
    summary["Participação (p.p.)"] = (
        summary["Série"].map(share_now).fillna(0) - summary["Série"].map(share_before)
    ) * 100
    return summary.nlargest(limit, "Total").reset_index(drop=True)


def filter_options(
    models: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    selected_segments: Iterable[str],
    selected_brands: Iterable[str],
    selected_categories: Iterable[str] = (),
) -> list[str]:
    frame = models[(models["competencia"] >= start) & (models["competencia"] <= end)]
    selected_segments = list(selected_segments)
    selected_brands = list(selected_brands)
    selected_categories = list(selected_categories)
    if selected_segments:
        frame = frame[frame["segmento"].isin(selected_segments)]
    else:
        return []
    if selected_brands:
        frame = frame[frame["marca"].isin(selected_brands)]
    if selected_categories:
        frame = frame[frame["categoria"].isin(selected_categories)]
    return sorted(frame["modelo"].dropna().unique().tolist())


def market_map(monthly: pd.DataFrame, period: str) -> pd.DataFrame:
    """Interval totals per detail combination, plus the year-over-year change of the latest period."""
    columns = detail_columns(monthly)
    if monthly.empty or not columns:
        return monthly
    totals = monthly.groupby(columns, as_index=False, observed=True)["Emplacamentos"].sum()
    compared = year_over_year(monthly, period)
    latest = compared["Periodo"].max()
    compared = compared[compared["Periodo"] == latest][
        columns + ["Variacao_anual", "Variacao_anual_percentual"]
    ]
    return totals.merge(compared, on=columns, how="left")
