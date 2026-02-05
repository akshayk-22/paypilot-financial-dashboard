from faker import Faker
import random as rd
import string

fake = Faker()
def generate_password(length):
    chars = string.ascii_letters + string.digits +string.punctuation
    password = ''
    for i in range(length):
        password +=''.join(rd.choice(chars))
    return password
    
def generate_username(fname, lname):
    return f'{fname.lower()}.{lname.lower()}{rd.randint(9, 1000)}'


def generate_account(acct_id):
    fname = fake.first_name()
    lname = fake.last_name()
    return {
        'id': acct_id,
        'username': generate_username(fname, lname),
        'password': generate_password(12),
        'first name': fname, 
        'last name': lname,
        'email': f'{fname.lower()}.{lname.lower()}{rd.randint(5,210)}@{fake.free_email_domain()}',
        'phone': fake.phone_number(),
        'birthdate': fake.date_of_birth(minimum_age=18, maximum_age=70).strftime('%Y-%M-%D'),
        'address': fake.address().replace("\n", ", ")
    }

def generate_advisor(acct_id):
    fname = fake.first_name()
    lname = fake.last_name()
    return{
        'id': acct_id,
        'username': generate_username(fname, lname),
        'password': generate_password(12),
        'first name': fname,
        'last name': lname,
        'email': f'{fname.lower()}.{lname.lower()}{rd.randint(5,210)}@{fake.domain_name()}',
        'phone': fake.phone_number()
    }


users = [generate_account(acct_id=i) for i in range(0, 30)]
advisors = [generate_advisor(acct_id=i) for i in range(15)]

#TODO bill data needs to be generated or created

def generate_bill(profile_id):
    return {
        'profile_id': profile_id, 
        'bill_provider': fake.company(),
        'description': fake.bs().capitalize(),
        'amount': round(rd.uniform(50.0, 500.0), 2),
        'due_date': fake.date_between(start_date='today', end_date='+30d').strftime('%Y-%m-%d'),
        'is_paid': rd.choice([0, 1])
    }