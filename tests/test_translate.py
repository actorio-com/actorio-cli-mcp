from typer.testing import CliRunner

from actorio_cli.commands.translate import translate
from actorio_cli.main import app

runner = CliRunner()


def test_full_webapp_url():
    url = (
        "https://app.actorio.com/products/search/"
        "?store=carrefour.es&roi_min=20&roi_max=500&similarity=2"
        "&size=LGT_ENV&size=SML_PAR&missing_fba=true&page=2"
    )
    command, warnings = translate(url)
    assert warnings == []
    assert command == (
        "actorio products search --store carrefour.es --roi-min 20 --roi-max 500 "
        "--similarity 2 --size LGT_ENV --size SML_PAR --missing-fba"
    )


def test_bare_query_string_defaults_to_products():
    command, _ = translate("keywords=ipad&price_max=99")
    assert command == "actorio products search ipad --price-max 99"


def test_keyword_param_becomes_positional():
    command, _ = translate("/products/search/?q=ipad case")
    assert command == "actorio products search 'ipad case'"


def test_kind_detection():
    assert translate("/products/favorites/?store=x.es")[0].startswith("actorio favorites search")
    assert translate("/products/amazon_search/?store=x.es")[0].startswith("actorio amazon search")
    assert translate("/products/reverse_search/?store=x.es")[0].startswith("actorio reverse search")


def test_unknown_param_warns():
    command, warnings = translate("/products/search/?mystery=1&price_max=5")
    assert "price-max 5" in command
    assert any("mystery" in w for w in warnings)


def test_boolean_false_is_dropped():
    command, _ = translate("/products/search/?missing_fba=false&multipack=1")
    assert "--missing-fba" not in command
    assert "--multipack" in command


def test_unrecognized_path_errors():
    result = runner.invoke(app, ["translate", "https://app.actorio.com/stores/"])
    assert result.exit_code == 1
    assert "Unrecognized search URL path" in result.output


def test_cli_output_is_one_line():
    result = runner.invoke(app, ["translate", "https://app.actorio.com/products/search/?store=carrefour.es"])
    assert result.exit_code == 0
    assert result.output.strip() == "actorio products search --store carrefour.es"
