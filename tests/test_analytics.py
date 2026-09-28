from pathlib import Path

import pandas as pd

from analytics import (
    ALL_SEGMENTS,
    UNCLASSIFIED,
    add_period_share,
    add_period_variation,
    aggregate_sales,
    growth_contribution,
    market_map,
    load_data,
    previous_year_label,
    year_over_year,
    rank_by_period,
    seasonality,
    share_by_period,
    summary_table,
    top_series,
)


ROOT = Path(__file__).resolve().parents[1]
MODELS, BRANDS = load_data(ROOT / "data")


def test_dataset_coverage():
    assert len(MODELS) == 6749
    assert len(BRANDS) == 1428
    assert MODELS["competencia"].nunique() == 68
    assert BRANDS["competencia"].nunique() == 68


def test_quarterly_brand_aggregation_uses_brand_totals():
    result, source = aggregate_sales(
        MODELS,
        BRANDS,
        pd.Timestamp("2021-01-01"),
        pd.Timestamp("2021-03-01"),
        "Trimestre",
        ["Marca"],
        ALL_SEGMENTS,
        ["FIAT"],
    )
    expected = BRANDS[
        (BRANDS["competencia"].between("2021-01-01", "2021-03-01"))
        & (BRANDS["marca"] == "FIAT")
    ]["quantidade"].sum()
    assert source == "marcas"
    assert result.to_dict("records") == [
        {"Periodo": "2021 T1", "Marca": "FIAT", "Emplacamentos": expected}
    ]


def test_model_and_segment_filter_uses_model_ranking():
    result, source = aggregate_sales(
        MODELS,
        BRANDS,
        pd.Timestamp("2025-01-01"),
        pd.Timestamp("2025-12-01"),
        "Ano",
        ["Marca", "Modelo"],
        ["Automóveis"],
        ["VW"],
        ["POLO"],
    )
    expected = MODELS[
        (MODELS["ano"] == 2025)
        & (MODELS["segmento"] == "Automóveis")
        & (MODELS["marca"] == "VW")
        & (MODELS["modelo"] == "POLO")
    ]["quantidade"].sum()
    assert source == "modelos"
    assert result.iloc[0].to_dict() == {
        "Periodo": "2025",
        "Marca": "VW",
        "Modelo": "POLO",
        "Emplacamentos": expected,
    }


def test_variation_is_calculated_within_each_brand():
    result, _ = aggregate_sales(
        MODELS,
        BRANDS,
        pd.Timestamp("2021-01-01"),
        pd.Timestamp("2022-12-01"),
        "Ano",
        ["Marca"],
        ALL_SEGMENTS,
        ["FIAT", "VW"],
    )
    compared = add_period_variation(result)
    for brand in ("FIAT", "VW"):
        rows = compared[compared["Marca"] == brand].sort_values("Periodo")
        assert pd.isna(rows.iloc[0]["Variacao"])
        assert rows.iloc[1]["Variacao"] == (
            rows.iloc[1]["Emplacamentos"] - rows.iloc[0]["Emplacamentos"]
        )
        expected = "▲ Aumento" if rows.iloc[1]["Variacao"] > 0 else "▼ Queda"
        assert rows.iloc[1]["Tendencia"] == expected


def _brand_result(start="2024-01-01", end="2024-12-01", period="Trimestre"):
    result, _ = aggregate_sales(
        MODELS,
        BRANDS,
        pd.Timestamp(start),
        pd.Timestamp(end),
        period,
        ["Marca"],
        ALL_SEGMENTS,
    )
    return result


def test_top_series_is_ordered_by_total_volume():
    result = _brand_result()
    ranked = top_series(result, 3)
    totals = result.groupby("Marca")["Emplacamentos"].sum()
    assert ranked == totals.nlargest(3).index.tolist()


def test_share_by_period_buckets_the_tail_and_sums_to_one():
    result = _brand_result()
    share = share_by_period(result, 5)
    assert "Outros" in set(share["Série"])
    assert set(share["Série"]) == set(top_series(result, 5)) | {"Outros"}
    per_period = share.groupby("Periodo")["Participacao"].sum()
    assert per_period.round(9).eq(1).all()
    assert share.groupby("Periodo")["Emplacamentos"].sum().tolist() == (
        result.groupby("Periodo")["Emplacamentos"].sum().tolist()
    )


def test_seasonality_splits_year_and_month():
    result = _brand_result(period="Mês")
    season = seasonality(result)
    assert season["Mes"].tolist() == list(range(1, 13))
    assert set(season["Ano"]) == {"2024"}
    assert season["Emplacamentos"].sum() == result["Emplacamentos"].sum()


def test_period_share_sums_to_one_inside_each_period():
    result = _brand_result()
    shared = add_period_share(result)
    per_period = shared.groupby("Periodo")["Participacao"].sum()
    assert per_period.round(9).eq(1).all()
    biggest = shared.sort_values("Participacao").iloc[-1]
    period_total = result[result["Periodo"] == biggest["Periodo"]]["Emplacamentos"].sum()
    assert biggest["Participacao"] == biggest["Emplacamentos"] / period_total


def test_every_model_has_a_body_type():
    assert not (MODELS["categoria"] == UNCLASSIFIED).any()
    assert MODELS.loc[MODELS["modelo"] == "STRADA", "categoria"].eq("Picape compacta").all()
    assert MODELS.loc[MODELS["modelo"] == "CRETA", "categoria"].eq("SUV compacto").all()
    # Mesmo nome, carroceria diferente conforme o segmento.
    doblo = MODELS[MODELS["modelo"] == "DOBLO"].groupby("segmento")["categoria"].first()
    assert doblo["Automóveis"] == "Minivan"
    assert doblo["Comerciais leves"] == "Furgão compacto"


def test_category_detail_matches_the_model_ranking():
    result, source = aggregate_sales(
        MODELS,
        BRANDS,
        pd.Timestamp("2025-01-01"),
        pd.Timestamp("2025-12-01"),
        "Ano",
        ["Categoria"],
    )
    assert source == "modelos"
    expected = MODELS[MODELS["ano"] == 2025].groupby("categoria")["quantidade"].sum()
    got = result.set_index("Categoria")["Emplacamentos"]
    assert got.to_dict() == expected.to_dict()


def test_category_filter_narrows_the_base():
    result, _ = aggregate_sales(
        MODELS,
        BRANDS,
        pd.Timestamp("2025-01-01"),
        pd.Timestamp("2025-12-01"),
        "Ano",
        ["Marca"],
        selected_categories=["SUV compacto"],
    )
    expected = MODELS[(MODELS["ano"] == 2025) & (MODELS["categoria"] == "SUV compacto")][
        "quantidade"
    ].sum()
    assert result["Emplacamentos"].sum() == expected


def test_previous_year_label_covers_every_period_format():
    assert previous_year_label("2024-07") == "2023-07"
    assert previous_year_label("2024 T3") == "2023 T3"
    assert previous_year_label("2024") == "2023"


def _monthly(start="2023-01-01", end="2024-12-01", details=("Marca",)):
    result, _ = aggregate_sales(
        MODELS, BRANDS, pd.Timestamp(start), pd.Timestamp(end), "Mês", list(details)
    )
    return result


def test_year_over_year_compares_with_the_same_month():
    monthly = _monthly()
    compared = year_over_year(monthly, "Mês")
    row = compared[(compared["Periodo"] == "2024-03") & (compared["Marca"] == "FIAT")].iloc[0]
    base = monthly[(monthly["Periodo"] == "2023-03") & (monthly["Marca"] == "FIAT")].iloc[0]
    assert row["Emplacamentos_anterior"] == base["Emplacamentos"]
    assert row["Variacao_anual"] == row["Emplacamentos"] - base["Emplacamentos"]
    # Primeiro ano não tem base de comparação.
    assert compared[compared["Periodo"] == "2023-01"]["Variacao_anual"].isna().all()


def test_partial_year_is_compared_with_the_same_months():
    """jan-ago/2026 contra jan-ago/2025, nunca contra 2025 inteiro."""
    monthly = _monthly("2025-01-01", "2026-08-01", details=())
    compared = year_over_year(monthly, "Ano")
    current = compared[compared["Periodo"] == "2026"].iloc[0]
    assert current["Meses"] == 8
    same_months = monthly[monthly["Periodo"].str.startswith("2025-")]
    same_months = same_months[same_months["Periodo"].str[-2:] <= "08"]
    assert current["Emplacamentos_anterior"] == same_months["Emplacamentos"].sum()
    full_2025 = monthly[monthly["Periodo"].str.startswith("2025-")]["Emplacamentos"].sum()
    assert current["Emplacamentos_anterior"] < full_2025


def test_quarter_labels_group_three_months():
    monthly = _monthly("2024-01-01", "2024-12-01", details=())
    compared = year_over_year(monthly, "Trimestre")
    assert sorted(compared["Periodo"]) == ["2024 T1", "2024 T2", "2024 T3", "2024 T4"]
    assert compared["Meses"].tolist() == [3, 3, 3, 3]


def test_rank_by_period_orders_from_the_biggest():
    result = _brand_result()
    ranked = rank_by_period(result)
    first_period = ranked[ranked["Periodo"] == ranked["Periodo"].min()]
    leader = first_period.nlargest(1, "Emplacamentos").iloc[0]
    assert leader["Posicao"] == 1
    assert set(first_period["Posicao"]) == set(range(1, len(first_period) + 1))


def test_growth_contribution_uses_the_latest_period():
    contribution = growth_contribution(_monthly(), "Ano", 5)
    assert set(contribution["Periodo"]) == {"2024"}
    assert len(contribution) == 5
    deltas = contribution["Variacao_anual"].abs()
    assert deltas.tolist() == sorted(deltas, reverse=True)


def test_summary_table_totals_and_share():
    monthly = _monthly("2024-01-01", "2024-12-01")
    summary = summary_table(monthly, "Trimestre", 5)
    biggest = summary.iloc[0]
    expected_total = monthly[monthly["Marca"] == biggest["Série"]]["Emplacamentos"].sum()
    assert biggest["Total"] == expected_total
    assert biggest["Participação"] == expected_total / monthly["Emplacamentos"].sum()
    assert len(biggest["Histórico"]) == 4  # quatro trimestres
    assert sum(biggest["Histórico"]) == expected_total


def test_market_map_totals_the_interval_and_carries_the_latest_growth():
    monthly = _monthly(details=("Marca", "Modelo"))
    result, _ = aggregate_sales(
        MODELS, BRANDS, pd.Timestamp("2023-01-01"), pd.Timestamp("2024-12-01"), "Ano",
        ["Marca", "Modelo"],
    )
    mapped = market_map(monthly, "Ano")
    row = mapped[(mapped["Marca"] == "FIAT") & (mapped["Modelo"] == "STRADA")].iloc[0]
    interval = result[(result["Marca"] == "FIAT") & (result["Modelo"] == "STRADA")]
    assert row["Emplacamentos"] == interval["Emplacamentos"].sum()
    last = interval[interval["Periodo"] == "2024"]["Emplacamentos"].iloc[0]
    before = interval[interval["Periodo"] == "2023"]["Emplacamentos"].iloc[0]
    assert row["Variacao_anual"] == last - before
    assert len(mapped) == len(result.groupby(["Marca", "Modelo"]))
