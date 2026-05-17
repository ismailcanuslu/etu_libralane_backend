from app.services.openlane_config_catalog import parse_readme_markdown, search_variables


SAMPLE = """
## Required variables

| Variable | Description |
|---------------|-------------------------------------------------------|
| `DESIGN_NAME` | The name of the top level module of the design |
| `VERILOG_FILES` | The path of the design's verilog files |

### Flow control

| Variable | Description |
|---------------|---------------------------------------------------------------|
| `FILL_INSERTION` | Enables fill cells insertion after cts (if enabled) .1 = Enabled, 0 = Disabled (Default: `1`)|
"""


def test_parse_required_and_category():
    cat = parse_readme_markdown(SAMPLE)
    assert cat["variables"]["DESIGN_NAME"]["required"] is True
    assert cat["variables"]["FILL_INSERTION"]["category"] == "flow_control"
    assert "1" in (cat["variables"]["FILL_INSERTION"]["default"] or "")


def test_search_prefix():
    cat = parse_readme_markdown(SAMPLE)
    keys = search_variables(cat, "FI", category="flow_control")
    assert "FILL_INSERTION" in keys
    keys_all = search_variables(cat, "DE")
    assert "DESIGN_NAME" in keys_all
