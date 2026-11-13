import argparse
import getpass
from sqlalchemy.exc import IntegrityError
import uuid
from .database import database, init_database, users
from .security import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create a fund account. Each account has its own fund records.")
    parser.add_argument("email")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if "@" not in email or len(email) > 254:
        parser.error("Enter a valid email address")
    password = getpass.getpass("Password (at least 8 characters): ")
    if len(password) < 8 or len(password) > 128:
        parser.error("Password must contain 8 to 128 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    init_database()
    try:
        with database() as connection:
            connection.execute(users.insert().values(id=str(uuid.uuid4()), email=email, password_hash=hash_password(password)))
    except IntegrityError:
        parser.error("An account already exists for that email")
    print(f"Account created for {email}")


if __name__ == "__main__":
    main()
