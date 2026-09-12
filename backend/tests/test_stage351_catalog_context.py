def test_stage351_catalog_context_is_defined():
    from pathlib import Path
    seed = Path(__file__).parents[1] / "app" / "seed.py"
    text = seed.read_text()
    assert "Corporate Filings" in text
    assert "Corporate Registry Data" in text
    assert "florida_data_lab" in text
    assert "raw.corporate_data" in text
    assert "8e516582-c3af-4f5e-81ad-35bdbcd55f83" in text
    assert "b025efd2-da4c-4384-9578-9a28f0f8cf2f" in text
