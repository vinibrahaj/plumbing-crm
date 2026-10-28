"""Bootstrap the first manager without shipping default credentials."""
import argparse
import getpass
import sqlite3

from .db import connect, init_db
from .security import hash_password


def main():
    parser = argparse.ArgumentParser(description='Create a Plumb CRM manager')
    parser.add_argument('--email', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    email, name = args.email.strip().lower(), args.name.strip()
    if not name or '@' not in email or email.startswith('@') or email.endswith('@'):
        parser.error('A name and valid email address are required')
    password = getpass.getpass('Password (at least 12 characters): ').strip()
    if len(password) < 12 or len(password) > 256:
        parser.error('Password must contain 12–256 characters')
    if password != getpass.getpass('Confirm password: ').strip():
        parser.error('Passwords do not match')
    init_db()
    try:
        with connect() as db:
            db.execute("INSERT INTO users(name,email,password_hash,role) VALUES (?,?,?,'manager')",
                       (name, email, hash_password(password)))
    except sqlite3.IntegrityError:
        parser.error('That email is already registered')
    print(f'Manager created: {email}')


if __name__ == '__main__':
    main()
