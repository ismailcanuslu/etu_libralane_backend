from app.services.text_format import merge_stream_field, normalize_model_markdown


def test_merge_preserves_leading_space_in_delta() -> None:
    assert merge_stream_field("Merhaba", " dunya") == "Merhaba dunya"


def test_merge_cumulative() -> None:
    assert merge_stream_field("Merhaba", "Merhaba dunya") == "Merhaba dunya"


def test_merge_delta_without_space_gets_space_for_word_boundary() -> None:
    assert merge_stream_field("adim", "Plan") == "adim Plan"


def test_merge_subword_no_extra_space() -> None:
    assert merge_stream_field("think", "ing") == "thinking"


def test_merge_turkish_word_boundary() -> None:
    assert merge_stream_field("Merhaba", "dunya") == "Merhaba dunya"


def test_merge_sentence_punctuation() -> None:
    assert merge_stream_field("Tamam.", "Sonraki") == "Tamam. Sonraki"


def test_normalize_markdown_headers() -> None:
    raw = "Giris\n## Adim 1\n- madde"
    out = normalize_model_markdown(raw)
    assert out is not None
    assert "\n\n## Adim 1" in out
