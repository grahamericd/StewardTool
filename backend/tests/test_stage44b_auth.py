from app.auth import hash_password, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("This is a strong test password 123!")
    assert encoded.startswith("scrypt$")
    assert verify_password("This is a strong test password 123!", encoded)
    assert not verify_password("Wrong password", encoded)


def test_password_hashes_use_random_salts():
    password = "This is a strong test password 123!"
    assert hash_password(password) != hash_password(password)
