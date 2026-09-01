"""Database connection and seeding."""
import os
import psycopg
from dotenv import load_dotenv
from auth import hash_password

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    try:
        return psycopg.connect(DATABASE_URL)
    except Exception as e:
        raise ConnectionError(f"Unable to connect: {e}")


def check_db():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
                return True
    except Exception as err:
        print("Database error:", err)
        return False


def seed_database():
    sql_statements = [
        # Drop existing tables in correct order (child tables first)
        "DROP TABLE IF EXISTS orders CASCADE;",
        "DROP TABLE IF EXISTS audit_logs CASCADE;",
        "DROP TABLE IF EXISTS products CASCADE;",
        "DROP TABLE IF EXISTS employees CASCADE;",
        "DROP TABLE IF EXISTS students CASCADE;",
        "DROP TABLE IF EXISTS departments CASCADE;",
        "DROP TABLE IF EXISTS users CASCADE;",

        # 1. Departments Table
        """
        CREATE TABLE departments (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            location VARCHAR(100),
            budget NUMERIC(12, 2)
        );
        """,
        """
        INSERT INTO departments (name, location, budget) VALUES
        ('Engineering', 'San Francisco', 1500000.00),
        ('Marketing', 'New York', 800000.00),
        ('Human Resources', 'Chicago', 400000.00),
        ('Sales', 'Austin', 1200000.00),
        ('Finance', 'New York', 900000.00);
        """,

        # 2. Employees Table
        """
        CREATE TABLE employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE,
            salary NUMERIC(10, 2),
            department_id INT REFERENCES departments(id),
            hire_date DATE
        );
        """,
        """
        INSERT INTO employees (name, email, salary, department_id, hire_date) VALUES
        ('Rahul Verma', 'rahul@example.com', 95000.00, 1, '2021-03-15'),
        ('Aman Sharma', 'aman@example.com', 88000.00, 1, '2022-01-10'),
        ('Priya Patel', 'priya@example.com', 92000.00, 1, '2020-06-20'),
        ('Neha Gupta', 'neha@example.com', 75000.00, 2, '2021-09-01'),
        ('Vikram Singh', 'vikram@example.com', 72000.00, 2, '2022-05-12'),
        ('Ananya Roy', 'ananya@example.com', 68000.00, 3, '2019-11-05'),
        ('Rohan Mehta', 'rohan@example.com', 85000.00, 4, '2021-02-28'),
        ('Kavya Nair', 'kavya@example.com', 90000.00, 4, '2020-08-14'),
        ('Siddharth Kumar', 'siddharth@example.com', 98000.00, 5, '2018-04-01'),
        ('Deepak Joshi', 'deepak@example.com', 65000.00, 3, '2023-02-10');
        """,



        # 4. Products Table
        """
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            price NUMERIC(10, 2),
            stock_quantity INT
        );
        """,
        """
        INSERT INTO products (name, category, price, stock_quantity) VALUES
        ('MacBook Pro M3', 'Electronics', 1999.99, 25),
        ('iPhone 15 Pro', 'Electronics', 1199.99, 50),
        ('Dell XPS 15', 'Electronics', 1499.99, 15),
        ('Ergonomic Chair', 'Furniture', 299.99, 40),
        ('Standing Desk', 'Furniture', 499.99, 20),
        ('Mechanical Keyboard', 'Accessories', 129.99, 100),
        ('Noise Cancelling Headphones', 'Accessories', 249.99, 60);
        """,

        # 5. Users Table (MUST be created before orders)
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'employee',
            name VARCHAR(100) NOT NULL,
            city VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # Insert default users with hashed passwords
        f"""
        INSERT INTO users (username, email, password_hash, role, name, city) VALUES
        ('admin', 'admin@example.com', '{hash_password("admin123")}', 'admin', 'Admin User', 'Delhi'),
        ('employee', 'employee@example.com', '{hash_password("employee123")}', 'employee', 'Employee User', 'Mumbai'),
        ('john_doe', 'john@example.com', '{hash_password("john123")}', 'employee', 'John Doe', 'New York'),
        ('jane_smith', 'jane@example.com', '{hash_password("jane123")}', 'employee', 'Jane Smith', 'London'),
        ('bob_wilson', 'bob@example.com', '{hash_password("bob123")}', 'employee', 'Bob Wilson', 'Sydney'),
        ('alice_brown', 'alice@example.com', '{hash_password("alice123")}', 'employee', 'Alice Brown', 'Toronto'),
        ('charlie_davis', 'charlie@example.com', '{hash_password("charlie123")}', 'employee', 'Charlie Davis', 'Berlin');
        """,

        # 6. Orders Table (references users and products)
        """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id),
            product_id INT REFERENCES products(id),
            quantity INT,
            total_amount NUMERIC(10, 2),
            order_date DATE
        );
        """,
        """
        INSERT INTO orders (user_id, product_id, quantity, total_amount, order_date) VALUES
        (1, 1, 1, 1999.99, '2024-01-15'),
        (1, 6, 2, 259.98, '2024-01-16'),
        (2, 2, 1, 1199.99, '2024-01-20'),
        (3, 4, 2, 599.98, '2024-02-01'),
        (4, 5, 1, 499.99, '2024-02-05'),
        (5, 3, 1, 1499.99, '2024-02-15'),
        (6, 7, 1, 249.99, '2024-03-01');
        """,
    ]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                for sql in sql_statements:
                    cursor.execute(sql)
                conn.commit()
        print("✅ Database seeded successfully!")
        print("\n📋 Default users:")
        print("   - admin / admin123 (admin role)")
        print("   - employee / employee123 (employee role)")
        print("   - john_doe / john123 (employee role)")
        print("   - jane_smith / jane123 (employee role)")
        print("   - bob_wilson / bob123 (employee role)")
        print("   - alice_brown / alice123 (employee role)")
        print("   - charlie_davis / charlie123 (employee role)")
    except Exception as err:
        print(f"❌ Error seeding database: {err}")


if __name__ == "__main__":
    seed_database()