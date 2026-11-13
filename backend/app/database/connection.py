
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

# Select database using DB_PROVIDER=local or DB_PROVIDER=azure
DB_PROVIDER = os.getenv("DB_PROVIDER", "local").strip().lower()

DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")


def get_connection():
    if DB_PROVIDER == "azure":
        server = os.getenv("AZURE_SQL_SERVER")
        database = os.getenv("AZURE_SQL_DATABASE")
        username = os.getenv("AZURE_SQL_USERNAME")
        password = os.getenv("AZURE_SQL_PASSWORD")

        if not all([server, database, username, password]):
            raise ValueError("Azure SQL configuration is incomplete. Check your .env file.")

        connection_string = (
            f"DRIVER={{{DRIVER}}};"
            f"SERVER=tcp:{server},1433;"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
        )

    elif DB_PROVIDER == "local":
        server = os.getenv("DB_SERVER", "localhost")
        database = os.getenv("DB_NAME", "VulnWeaveDB")

        connection_string = (
            f"DRIVER={{{DRIVER}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )

    else:
        raise ValueError("Invalid DB_PROVIDER. Choose 'local' or 'azure'.")

    return pyodbc.connect(connection_string)


def test_connection():
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT DB_NAME()")

        database_name = cursor.fetchone()[0]

        cursor.close()
        connection.close()

        return {
            "success": True,
            "database": database_name,
            "provider": DB_PROVIDER
        }

    except Exception as error:
        return {
            "success": False,
            "provider": DB_PROVIDER,
            "error": str(error)
        }
