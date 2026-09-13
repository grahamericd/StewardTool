from sqlalchemy import URL


def test_sqlalchemy_url_handles_special_characters_in_password():
    url = URL.create(
        drivername="postgresql+psycopg",
        username="steward",
        password="P@ss:word/with?special#chars",
        host="db",
        port=5432,
        database="ai_data_steward",
    )
    assert url.host == "db"
    assert url.username == "steward"
    assert url.password == "P@ss:word/with?special#chars"
