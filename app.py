from flask import Flask, jsonify, render_template, request, redirect, session, g, flash, url_for
from datetime import datetime
import sqlite3
import random
import os

# Initialize Flask application and database
app = Flask(__name__)
app.secret_key = os.urandom(24)
DATABASE = os.path.join(os.getcwd(), 'paypilot.db')

# Helper function to connect to the database
def connect_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db   

# Close the database connection after each request
@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_database', None)
    if db:
        db.close()

# Login route
@app.route('/', methods=['GET', 'POST'])
def web_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = connect_db()
        cursor = db.cursor()

        cursor.execute(
            "SELECT * FROM Account WHERE username = ? AND password = ?", 
            (username, password)
        )
        user = cursor.fetchone()

        if user:
            acct_id = user['acct_id']
            session['user_id'] = acct_id

            #Checking if user is customer:
            cursor.execute(
                "SELECT * FROM CUSTOMER WHERE acct_id = ?", (acct_id,))
            if cursor.fetchone():
                return redirect('/dashboard')
            
            #Checking if user is admin:
            cursor.execute(
                "SELECT * FROM ADMIN WHERE acct_id = ?", (acct_id,))
            if cursor.fetchone():
                return redirect('/admin_reports')
            
            # Check if user is Financial Advisor
            cursor.execute(
                "SELECT * FROM FINANCIAL_ADVISOR WHERE acct_id = ?", (acct_id,))
            if cursor.fetchone():
                return redirect('/advisor_dashboard')
            
            #Account exists but no assigned role
            return "Existing account has no current role", 403
            
        else:
            return "Invalid credentials", 401

    return render_template('login.html')

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        bdate = request.form['bdate']
        f_name = request.form['f_name']
        l_name = request.form['l_name']

        db = connect_db()
        cursor = db.cursor()
        # Check if username already exists
        exists = db.execute(
            "SELECT 1 FROM ACCOUNT WHERE username = ?",
            (username,)
        ).fetchone()
        if exists:
            error = "Username already taken"
        else:
            try:
                # Insert new account
                db.execute(
                    "INSERT INTO ACCOUNT (username, password) VALUES (?, ?)",
                    (username, password)
                )
                acct_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                            # Insert into CUSTOMER
                db.execute("""
                    INSERT INTO CUSTOMER (acct_id, f_name, l_name, email, phone, b_date, addr)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (acct_id, f_name, l_name, email, phone, bdate, address))

                # Get customer_id
                customer_id = db.execute("SELECT customer_id FROM CUSTOMER WHERE acct_id = ?", (acct_id,)).fetchone()[0]

                # Insert into FINANCIAL_PROFILE
                db.execute("INSERT INTO FINANCIAL_PROFILE (customer_id) VALUES (?)", (customer_id,))
                db.commit()

                # login the new user
                acct_id = acct_id
                session['user_id'] = acct_id
                user = cursor.execute("SELECT * FROM CUSTOMER WHERE acct_id = ?", (acct_id,)).fetchone()
                
                if user:
                    return redirect('/dashboard')
                else:      
                    error= 'An unexpected error occurred during registration. Please try again.'
                    return render_template('/register.html', error)
            except Exception as e:
                error = f'Registration failed: {e}'
                return render_template('/register.html', error=error)
            
    return render_template('register.html', error=error)

# Dashboard route
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect('/')
    acct_id = session['user_id']

    db = connect_db()

    # Get customers profile_id
    cursor = db.execute("""
        SELECT c.f_name, f.profile_id, c.advisor_id
        FROM CUSTOMER AS c
        JOIN FINANCIAL_PROFILE AS f 
          ON c.customer_id = f.customer_id
        WHERE c.acct_id = ?
    """, (session['user_id'],))
    result = cursor.fetchone()

    if not result:
        return "Customer profile not found", 404

    cust_name = result['f_name']
    profile_id = result['profile_id']
    current_adv_id = result['advisor_id']

# Advisor-assignment form
    if request.method == 'POST' and request.form.get('action') == 'assign_advisor':
        # pick a random advisor from the table
        adv_rows = db.execute("SELECT advisor_id FROM FINANCIAL_ADVISOR").fetchall()
        all_ids  = [r['advisor_id'] for r in adv_rows]
        new_adv_id = random.choice(all_ids) if all_ids else None

        if new_adv_id:
            # re-fetch the old advisor_id
            old_row = db.execute(
                "SELECT advisor_id FROM CUSTOMER WHERE acct_id = ?",
                (acct_id,)
            ).fetchone()
            old_adv_id = old_row['advisor_id'] if old_row else None

            # delete old pairs if present
            if old_adv_id:
                db.execute(
                    "DELETE FROM ADVISOR_REVIEWS WHERE advisor_id = ? AND profile_id = ?",
                    (old_adv_id, profile_id)
                )

            # update CUSTOMER.advisor_id
            db.execute(
                "UPDATE CUSTOMER SET advisor_id = ? WHERE acct_id = ?",
                (new_adv_id, acct_id)
            )
            # insert new mapping into ADVISOR_REVIEWS
            db.execute(
                "INSERT INTO ADVISOR_REVIEWS (advisor_id, profile_id) VALUES (?, ?)",
                (new_adv_id, profile_id)
            )

            db.commit()
            flash("A financial advisor has been assigned!", "success")

        return redirect('/dashboard')
    
    # Looks for current advisor assignment
    current_advisor = None
    if current_adv_id:
        current_advisor = db.execute("""
            SELECT advisor_id, f_name, l_name, phone
            FROM FINANCIAL_ADVISOR
            WHERE advisor_id = ?
        """, (current_adv_id,)).fetchone()
        
    # Gets full list of available advisors to assign
    advisors = db.execute("""
        SELECT advisor_id, f_name, l_name
        FROM FINANCIAL_ADVISOR
        ORDER BY l_name, f_name
    """).fetchall()

    action = request.form.get('action')
    if request.method == 'POST':
        #Insert functionality
        if action == 'insert':
            bill_provider = request.form['bill_provider']
            description = request.form['description']
            amount = request.form['amount']
            due_date = request.form['due_date']
            has_reminder = 1 if 'has_reminder' in request.form else 0

            db.execute("""
                INSERT INTO BILL (profile_id, bill_provider, description, amount, due_date, has_reminder)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (profile_id, bill_provider, description, amount, due_date, has_reminder))
            db.commit()

        #Delete functionality
        elif action == 'delete':
            bill_id = request.form.get('bill_id')

            if bill_id:
                db.execute("DELETE FROM BILL WHERE bill_id = ? AND profile_id = ?", (bill_id, profile_id))
                db.commit()
        
        #Update functionality
        elif action == 'update':
            bill_id = request.form['bill_id']
            bill_provider = request.form['bill_provider']
            description = request.form['description']
            amount = request.form['amount']
            due_date = request.form['due_date']
            has_reminder = 1 if 'has_reminder' in request.form else 0
            is_paid = 1 if 'is_paid' in request.form else 0

            query ="""UPDATE BILL
                    SET bill_provider = ?, description = ?, amount = ?, due_date = ?, has_reminder = ?, is_paid = ?
                    WHERE bill.bill_id = ? AND bill.profile_id = ?"""
            try: 
                db.execute(query, (bill_provider, description, amount, due_date, has_reminder, is_paid, bill_id, profile_id))
                db.commit()
            except sqlite3.Error as e:
                print(f'[SQLite Error] {e}')
                   
    # Load all bills for this profile
    bills = db.execute("""
        SELECT bill_id, bill_provider, description,
               amount, due_date, has_reminder, is_paid
        FROM BILL
        WHERE profile_id = ?
        ORDER BY due_date ASC
    """, (profile_id,)).fetchall()

    db.close()

    return render_template(
        'dashboard.html',
        name=cust_name,
        bills=bills,
        current_advisor=current_advisor,
        advisors=advisors
    )

# Admin dashboard 
@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user_id' not in session:
        return redirect('/')

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("SELECT f_name, l_name FROM ADMIN WHERE acct_id = ?", (session['user_id'],))
    admin = cursor.fetchone()

    if not admin:
        return "Not admin profile", 403

    message = None

    if request.method == 'POST':
        role = request.form.get('role')  # either 'advisor' or 'admin'
        f_name = request.form.get('f_name')
        l_name = request.form.get('l_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        username = request.form.get('username')
        password = request.form.get('password')

        message = create_account(role, username, password, f_name, l_name, email, phone)

    advisors = get_advisors()
    admins = get_admins()

    return render_template(
        'admin_dashboard.html',
        admin=admin,
        message=message,
        advisors=advisors,
        admins=admins
    )

#delete admin account from admin dashboard
@app.route('/delete/<role>/<int:acct_id>', methods=['POST'])
def delete_account_route(role, acct_id):
    if role not in ['admin', 'advisor']:
        return "Invalid role", 400

    if acct_id == session.get('user_id'):
        flash("You cannot delete your own account.")
        return redirect(url_for('admin_dashboard'))

    message = delete_account(acct_id, role)
    flash(message)
    return redirect(url_for('admin_dashboard'))

#Admin Dashbaord Helper Function 1: Displaying advisors
def get_advisors():
    db = connect_db()
    return db.execute("SELECT * FROM FINANCIAL_ADVISOR").fetchall()

#Admin Dashboard Helper Function 2: Displaying admins
def get_admins():
    db = connect_db()
    return db.execute("SELECT * FROM ADMIN").fetchall()

# Editing account dashboard from admin dashboard
@app.route('/edit/<role>/<int:acct_id>')
def edit_account(role, acct_id):
    user = get_account_role(role, acct_id)
    if not user:
        return "Account not found", 404
    return render_template('account_edit.html', role=role, user=user)

# Admin Dashboard Helper Function 3: Creating accounts
def create_account(user_role, username, password, f_name, l_name, email, phone):
    db = connect_db()
    cursor = db.cursor()

    # Check if username already exists
    existing_user = cursor.execute(
        "SELECT 1 FROM ACCOUNT WHERE username = ?", (username,)
    ).fetchone()

    if existing_user:
        return "Username already taken. Try another one."

    try:
        # Insert into Account table
        cursor.execute(
            "INSERT INTO ACCOUNT (username, password) VALUES (?, ?)",
            (username, password)
        )
        acct_id = cursor.lastrowid

        # Insert into the appropriate user role table
        if user_role == 'advisor':
            cursor.execute(
                "INSERT INTO FINANCIAL_ADVISOR (acct_id, f_name, l_name, email, phone) VALUES (?, ?, ?, ?, ?)",
                (acct_id, f_name, l_name, email, phone)
            )
        elif user_role == 'admin':
            cursor.execute(
                "INSERT INTO ADMIN (acct_id, f_name, l_name, email, phone) VALUES (?, ?, ?, ?, ?)",
                (acct_id, f_name, l_name, email, phone)
            )

        db.commit()
        return "Account created successfully"
    
    except sqlite3.Error as e:
        db.rollback()
        return f"Error creating account: {e}"

# Admin Dashboard Helper Function 4: Deleting accounts
def delete_account(acct_id, user_role):
    db = connect_db()
    cursor = db.cursor()

    if user_role == 'advisor':
        cursor.execute("DELETE FROM FINANCIAL_ADVISOR WHERE acct_id = ?", (acct_id,))

    elif user_role == 'admin':
        cursor.execute("DELETE FROM ADMIN WHERE acct_id = ?", (acct_id,))

    # Delete from Account table
    cursor.execute("DELETE FROM ACCOUNT WHERE acct_id = ?", (acct_id,))
    
    db.commit()
    return "Account has been deleted successfully"

# Admin Dashboard Helper Function 5: Updating accounts
def update_account(role, acct_id, f_name, l_name, email, phone):
    db = connect_db()
    table = 'ADMIN' if role == 'admin' else 'FINANCIAL_ADVISOR'
    db.execute(f"""
        UPDATE {table}
        SET f_name = ?, l_name = ?, email = ?, phone = ?
        WHERE acct_id = ?
    """, (f_name, l_name, email, phone, acct_id))
    db.commit()
    return "Account has been updated successfully"

#Admin Dashboard Helper Function 6: Finding out role of account
def get_account_role(user_role, acct_id):
    db = connect_db()
    table = 'ADMIN' if user_role == 'admin' else 'FINANCIAL_ADVISOR'
    return db.execute(f"SELECT * FROM {table} WHERE acct_id = ?", (acct_id,)).fetchone()

#Edit account dashboard
@app.route('/update/<role>/<int:acct_id>', methods=['POST'])
def update_account_info(role, acct_id):
    f_name = request.form.get('f_name')
    l_name = request.form.get('l_name')
    email = request.form.get('email')
    phone = request.form.get('phone')

    update_account(role, acct_id, f_name, l_name, email, phone)
    flash(f"{role.capitalize()} account updated successfully.")
    return redirect(url_for('admin_dashboard'))

# Advisor Dashboard
@app.route('/advisor_dashboard', methods=['GET'])
def advisor_dashboard():
    # Ensure advisor is logged in
    if 'user_id' not in session:
        return redirect('/')

    db = connect_db()
    acct_id = session['user_id']

    # Confirm this user is a financial advisor
    advisor = db.execute(
        "SELECT * FROM FINANCIAL_ADVISOR WHERE acct_id = ?",
        (acct_id,)
    ).fetchone()
    if not advisor:
        db.close()
        return "Not a financial advisor profile", 403
    
    # searches all customers assigned to this advisor
    cust_rows = db.execute("""
      SELECT c.customer_id, c.f_name, c.l_name, fp.profile_id
      FROM CUSTOMER AS c
      JOIN FINANCIAL_PROFILE AS fp
        ON c.customer_id = fp.customer_id
      WHERE c.advisor_id = ?
      ORDER BY c.l_name, c.f_name
    """, (advisor['advisor_id'],)).fetchall()
    customers = [dict(r) for r in cust_rows]

    # read the dropdown’s selected profile_id
    selected_profile = request.args.get('profile_id', type=int)

    # build a dynamic WHERE clause and parameters list
    owner_filter = "c.advisor_id = ?"
    params = [advisor['advisor_id']]
    if selected_profile:
        owner_filter += " AND fp.profile_id = ?"
        params.append(selected_profile)

    # Determine current month/year
    current_month = datetime.now().strftime('%m')
    current_year  = datetime.now().strftime('%Y')

    # Fetch all bills due this month for this advisor’s customers
    bills_query = f"""
       SELECT b.bill_id, b.bill_provider, b.description,
              b.amount, b.due_date, b.is_paid,
              c.f_name, c.l_name
       FROM BILL AS b
       JOIN FINANCIAL_PROFILE AS fp ON b.profile_id = fp.profile_id
       JOIN CUSTOMER           AS c  ON fp.customer_id = c.customer_id
       WHERE {owner_filter}
         AND strftime('%m', b.due_date) = ?
         AND strftime('%Y', b.due_date) = ?
       ORDER BY b.due_date ASC
    """
    month_params = params + [current_month, current_year]
    rows = db.execute(bills_query, month_params).fetchall()
    bills = [dict(r) for r in rows]

    # Compute summary statistics
    total_bills  = len(bills)
    paid_bills   = sum(1 for b in bills if b['is_paid'])
    unpaid_bills = total_bills - paid_bills
    amounts      = [b['amount'] for b in bills]

    if amounts:
        min_bill = min(amounts)
        max_bill = max(amounts)
        avg_bill = round(sum(amounts) / total_bills, 2)
    else:
        min_bill = max_bill = avg_bill = 0

    # Gathers only past due bills
    past_due_query = f"""
      SELECT COALESCE(SUM(b.amount),0) AS total
      FROM BILL AS b
      JOIN FINANCIAL_PROFILE AS fp ON b.profile_id = fp.profile_id
      JOIN CUSTOMER           AS c  ON fp.customer_id = c.customer_id
      WHERE {owner_filter}
        AND b.is_paid = 0
        AND date(b.due_date) < date('now')
    """
    past_due_total = db.execute(past_due_query, params).fetchone()['total']
    
    # Gathers full bill history
    history_query = f"""
      SELECT b.bill_id, b.bill_provider, b.description,
             b.amount, b.due_date, b.is_paid,
             c.f_name, c.l_name
      FROM BILL AS b
      JOIN FINANCIAL_PROFILE AS fp ON b.profile_id = fp.profile_id
      JOIN CUSTOMER           AS c  ON fp.customer_id = c.customer_id
      WHERE {owner_filter}
      ORDER BY b.due_date ASC
    """
    history_bills = [dict(r) for r in db.execute(history_query, params).fetchall()]

    db.close()

    # Renders to html file
    return render_template(
        'advisor_dashboard.html',
        advisor=advisor,
        customers=customers,
        selected_profile=selected_profile,
        bills=bills,
        total_bills=total_bills,
        paid_bills=paid_bills,
        unpaid_bills=unpaid_bills,
        min_bill=min_bill,
        max_bill=max_bill,
        avg_bill=avg_bill,
        past_due_total=past_due_total,
        history_bills=history_bills
    )

# Advanced settings route
@app.route('/advanced-settings', methods=['GET', 'POST'])
def advanced_settings():
    if 'user_id' not in session:
        return redirect('/')

    db = connect_db()
    acct_id = session['user_id']

    role = None  # Flag to track  user role

    # Trying Customer
    user = db.execute("""
        SELECT c.f_name, c.l_name, a.username
        FROM Customer c
        JOIN Account a ON c.acct_id = a.acct_id
        WHERE c.acct_id = ?
    """, (acct_id,)).fetchone()
    if user:
        role = 'customer'

    # Trying Financial Advisor
    if not user:
        user = db.execute("""
            SELECT f.f_name, f.l_name, a.username
            FROM Financial_Advisor f
            JOIN Account a ON f.acct_id = a.acct_id
            WHERE f.acct_id = ?
        """, (acct_id,)).fetchone()
        if user:
            role = 'advisor'

    # Trying Admin
    if not user:
        user = db.execute("""
            SELECT ad.f_name, ad.l_name, a.username
            FROM Admin ad
            JOIN Account a ON ad.acct_id = a.acct_id
            WHERE ad.acct_id = ?
        """, (acct_id,)).fetchone()
        if user:
            role = 'admin'

    if not user:
        return "User profile not found", 404

    if request.method == 'POST':
        new_username = request.form['username']
        new_password = request.form['password']

        existing = db.execute("""
            SELECT acct_id FROM Account WHERE username = ? AND acct_id != ?
        """, (new_username, acct_id)).fetchone()

        if existing:
            flash("Username already taken. Choose another one.")
        else:
            db.execute("""
                UPDATE Account SET username = ?, password = ? WHERE acct_id = ?
            """, (new_username, new_password, acct_id))
            db.commit()
            flash("Account information updated successfully.")
            return redirect('/advanced-settings')

    return render_template('advanced_settings.html', user=user, role=role)

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ADVISOR / CUSTOMER STATS:
# Finds number of bills due this month for
# the specified profile
def get_num_bills(profile_id):
    db = connect_db()
    current_month = datetime.now().strftime('%m')
    current_year = datetime.now().strftime('%Y')

    result = db.execute("""SELECT COUNT(*)
                        FROM BILL
                        WHERE profile_id = ? 
                        AND strftime('%m', due_date) = ?
                        AND strftime('%Y', due_date) = ? """, 
                        (profile_id, current_month, current_year)).fetchone()[0]

    return result


# ADVISOR STATS:
# Calculates the sum total due in bills for the
# specified profile during the specified month. 
def get_total_bill_amount(profile_id, month, year):
    db = connect_db()
    result = db.execute(
        """SELECT SUM(amount) 
        FROM BILL WHERE profile_id = ? 
        AND strftime('%m', due_date) = ? 
        AND strftime('%Y', due_date) = ?""", 
        (profile_id, month, year)).fetchone()[0]
    return result
    


# ADVISOR / CUSTOMER STATS:
# Finds total number of bills due this month and 
# specifies how many have been paid and how many are unpaid.
def bill_progress(profile_id, month, year):
    db = connect_db()

    # get total number of bills associated w this profile
    query = """SELECT COUNT(*)
    FROM BILL
    WHERE profile_id = ?
    AND strftime('%m', due_date) = ?
    AND strftime('%Y', due_date) = ?"""
    num_total = db.execute(query, (profile_id, month, year)).fetchone()[0]

    # find number that have been marked as paid
    paid_query = """SELECT COUNT(*)
    FROM BILL
    WHERE profile_id = ?
    AND strftime('%m', due_date) = ?
    AND strftime('%Y', due_date) = ?
    AND is_paid = ?"""
    num_paid = db.execute(paid_query, (profile_id, month, year, 1)).fetchone()[0]
    num_unpaid = num_total - num_paid # calculate number of unpaid bills
    return ({'num_total_bills':num_total, 'num_paid_bills': num_paid, 'num_unpaid_bills':num_unpaid})


# ADVISOR STATS:
# Finds the most expensive bill due this month 
# for the speicifed profile_id
def get_max_bill(profile_id, month, year):
    db = connect_db()
    query = """SELECT MAX(amount)
    FROM BILL
    WHERE profile_id = ? 
    AND strftime('%m', due_date) = ?
    AND strftime('%Y', due_date) = ?"""
    result = db.execute(query, (profile_id, month, year)).fetchone()[0]

    return result

# ADVISOR STATS:
# Finds the least expensive bill due this month 
# for the speicifed profile_id
def get_min_bill(profile_id, month, year):
    db = connect_db()
    result = db.execute(
        """SELECT MIN(amount)
            FROM BILL
            WHERE profile_id = ? 
            AND strftime('%m', due_date) = ?
            AND strftime('%Y', due_date) = ?""", 
            (profile_id, month, year)).fetchone()[0]
    return result

#ADMIN STATS dashboard route:
@app.route('/admin_reports', methods=['GET'])
def admin_stats():
    if 'user_id' not in session:
        return redirect('/login')

    db = connect_db()
    cursor = db.cursor()

    cursor.execute("SELECT f_name, l_name FROM ADMIN WHERE acct_id = ?", (session['user_id'],))
    admin = cursor.fetchone()

    cursor.execute("SELECT acct_id, f_name, l_name FROM FINANCIAL_ADVISOR")
    advisors = cursor.fetchall()

    advisor_id = request.args.get('advisor_id')
    chosen_advisor = int(advisor_id) if advisor_id else None

   #Initializing values to show in the admin reports page
    managed = None
    count_customers = None
    min_customers = None
    max_customers = None
    avg_customers = None

    if chosen_advisor:
        # ADMIN STAT 1: SUM - Total sum of all bill amounts of customers assigned to an advisor
        managed = cursor.execute(" SELECT SUM(b.amount) FROM BILL b JOIN FINANCIAL_PROFILE fp ON b.profile_id = fp.profile_id JOIN CUSTOMER c ON fp.customer_id = c.customer_id WHERE c.advisor_id = ?", (chosen_advisor,)).fetchone()[0] or 0

        # ADMIN STAT 2: COUNT - Total number of customers assigned to an advisor
        cursor.execute("SELECT COUNT(*) FROM CUSTOMER WHERE advisor_id = ?", (chosen_advisor,))
        count_customers = cursor.fetchone()[0]

        #ADMIN STAT 3,4,5: MIN, MAX, AVG - Min, Max, and Average number of customers assigned to each advisor
        cursor.execute("""
            SELECT MIN(customer_count), MAX(customer_count), ROUND(AVG(customer_count), 2)
            FROM (
                SELECT COUNT(*) as customer_count
                FROM CUSTOMER
                GROUP BY advisor_id
            )
        """)
        min_customers = count_customers
        max_customers = count_customers
        avg_customers = count_customers

    db.close()

    return render_template(
        'admin_reports.html',
        admin=admin,
        advisors=advisors,
        selected_advisor=chosen_advisor,
        sum_managed=managed,
        count_customers=count_customers,
        min_customers=min_customers,
        max_customers=max_customers,
        avg_customers=avg_customers
    )


if __name__ == '__main__':
    # Running the flask app       
    app.run(debug=True)

    '''
#Creating admin account, only if it doesn't exist
    with sqlite3.connect(DATABASE) as db:
        db.row_factory = sqlite3.Row
        cursor = db.cursor()

        check_admin = cursor.execute(""" 
            SELECT a.acct_id 
            FROM Account a
            JOIN ADMIN ad ON a.acct_id = ad.acct_id
            WHERE a.username = ? OR ad.email = ? 
        """, ("test.admin123", "testadmin@paypilot.com")).fetchone()

        if not check_admin:
            try:
                cursor.execute("""
                    INSERT INTO Account (username, password) 
                    VALUES (?, ?)
                """, ("test.admin123", "admin123!@#"))
                acct_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO Admin (acct_id, f_name, l_name, email, phone)
                    VALUES (?, ?, ?, ?, ?)
                """, (acct_id, "Test", "Admin", "testadmin@paypilot.com", "1234567890"))

                db.commit()
                print("Admin account created successfully.") #if created successfully

            except sqlite3.Error as e:
                db.rollback()
                print(f"Error creating admin account: {e}") #if account is not created

        else:
            print("Admin account already exists.")

            '''
