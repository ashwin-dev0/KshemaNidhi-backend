import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"{salt}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
