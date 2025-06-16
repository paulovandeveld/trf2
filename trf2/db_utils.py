import os
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine, text
# from airflow.hooks.base import BaseHook  # Uncomment when running in Airflow


def fetch_process_numbers():
    """Return list of process numbers from SQL Server."""
    try:
        # --- Airflow implementation ---
        # connection = BaseHook.get_connection("sqlserver_conn")
        # user = connection.login
        # password = connection.password
        # server = connection.host
        # database = connection.schema
        # connection_string = (
        #     f"mssql+pyodbc://{user}:{password}@{server}:1433/{database}"
        #     "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes&Connection Timeout=60&MARS_Connection=yes"
        # )

        # --- Local implementation ---
        user = os.getenv("SQLSERVER_USER")
        password = os.getenv("SQLSERVER_PASSWORD")
        server = os.getenv("SQLSERVER_HOST")
        database = os.getenv("SQLSERVER_DB")
        connection_string = (
            f"mssql+pyodbc://{user}:{password}@{server}:1433/{database}"
            "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes&Connection Timeout=60&MARS_Connection=yes"
        )

        engine = create_engine(
            connection_string,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )

        data_anterior = (datetime.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        query = """
            SELECT TOP 20 numero_processo
            FROM dbo.cnjComunicacoesProcessuais c
            WHERE tribunal = 'TRF2' AND data_disponibilizacao = :data_disponibilizacao
               AND NOT EXISTS (
                  SELECT 1
                  FROM pje.Processos p
                  WHERE p.cnj = c.numero_processo
              );
        """

        with engine.connect() as conn:
            result = conn.execute(text(query), {"data_disponibilizacao": data_anterior})
            df = pd.DataFrame(result.fetchall(), columns=result.keys())

        return df["numero_processo"].dropna().unique().tolist()

    except Exception as e:
        raise Exception(f"Erro ao extrair numero_processo: {e}")
