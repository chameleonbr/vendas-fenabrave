from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def run_app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()


def widget(app, kind, label):
    """Widgets are indexed by render order, which shifts when tabs change; find by label."""
    return next(item for item in getattr(app, kind) if item.label == label)


def test_app_starts_with_default_filters():
    app = run_app()
    assert not app.exception
    assert app.title[0].value == "Emplacamentos de veículos — Fenabrave"
    assert app.dataframe


def test_app_renders_charts_without_detail_columns():
    app = run_app()
    widget(app, "multiselect", "Detalhar por").set_value([]).run()
    assert not app.exception
    assert app.tabs


def test_app_renders_in_percent_mode():
    app = run_app()
    widget(app, "radio", "Exibir valores como").set_value("Percentual").run()
    assert not app.exception
    assert app.tabs


def test_app_detailed_by_body_type():
    app = run_app()
    widget(app, "multiselect", "Detalhar por").set_value(["Categoria"]).run()
    assert not app.exception
    assert app.tabs


def test_app_filtered_by_body_type():
    app = run_app()
    widget(app, "multiselect", "Carroceria").set_value(["SUV compacto"]).run()
    assert not app.exception
    assert not app.warning
    assert app.dataframe


def test_treemap_hierarchy_can_be_changed():
    app = run_app()
    widget(app, "multiselect", "Hierarquia do mapa").set_value(["Categoria", "Marca"]).run()
    assert not app.exception
    assert app.dataframe
