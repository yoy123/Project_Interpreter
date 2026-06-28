from project_interpreter.models import utc_now


def test_utc_now_returns_iso_string() -> None:
    assert "T" in utc_now()
