import sqlite3
import os
from generate_data import users, advisors, generate_bill

DATABASE = 'paypilot.db'

def initialize_database(db_path='paypilot.db', file='init_db.sql'):
    if os.path.exists(db_path):
        os.remove(db_path)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute('PRAGMA foreign_keys=ON;')
            with open(file, 'r') as f:
                sql_script = f.read()
            conn.executescript(sql_script)
        print(f'Database successfully initialized and saved to {db_path}')
    except sqlite3.Error as e:
        print(f'[Init DB Error] {e}')
        exit(1)

def create_connection():
    try:
        connection = sqlite3.connect(DATABASE)
        connection.execute('PRAGMA foreign_keys=ON;')
        print(f'Connection to {DATABASE} successful.')
        return connection
    except sqlite3.Error as error:
        print(f'Error connecting to {DATABASE} error code: {error}')
        return None

if __name__ == '__main__':
    initialize_database()

    print('Inserting advisor data...')
    conn = create_connection()
    if conn is None:
        print('Database connection failed. Exiting...')
        exit(1)
    cursor = conn.cursor()

    advisor_ids = []
    for advisor in advisors:
        cursor.execute(
            "INSERT INTO ACCOUNT (username, password) VALUES (?, ?)",
            (advisor['username'], advisor['password'])
        )
        acct_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO FINANCIAL_ADVISOR (acct_id, f_name, l_name, email, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (acct_id, advisor['first name'], advisor['last name'], advisor['email'], advisor['phone'])
        )
        advisor_id = cursor.lastrowid
        advisor_ids.append(advisor_id)

    print('Inserting customer data...')
    profile_ids = []
    for user in users:
        cursor.execute(
            "INSERT INTO ACCOUNT (username, password) VALUES (?, ?)",
            (user['username'], user['password'])
        )
        acct_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO CUSTOMER (acct_id, f_name, l_name, email, phone, b_date, addr)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (acct_id, user['first name'], user['last name'], user['email'], user['phone'], user['birthdate'], user['address'])
        )
        customer_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO FINANCIAL_PROFILE (customer_id) VALUES (?)""",
            (customer_id,)
        )
        profile_id = cursor.lastrowid
        profile_ids.append(profile_id)
        for _ in range(2):
            bill = generate_bill(profile_id)
            cursor.execute(
                """INSERT INTO BILL (profile_id, bill_provider, description, amount, due_date, is_paid)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    bill['profile_id'],
                    bill['bill_provider'],
                    bill['description'],
                    bill['amount'],
                    bill['due_date'],
                    bill['is_paid']
                )
            )
    
    conn.commit()
    conn.close()
    print('Database population complete.')