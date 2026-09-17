-- db/init/01-create-databases.sql
-- Un rôle par service, propriétaire de sa seule base.

SELECT 'CREATE ROLE mlflow LOGIN PASSWORD ' || quote_literal(:'mlflow_pwd')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mlflow')\gexec

SELECT 'CREATE ROLE airflow LOGIN PASSWORD ' || quote_literal(:'airflow_pwd')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'airflow')\gexec

SELECT 'CREATE DATABASE mlflow OWNER mlflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow')\gexec

SELECT 'CREATE DATABASE airflow OWNER airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec

-- Sans ça, tout le monde peut se connecter partout : PUBLIC dispose de
-- CONNECT par défaut sur chaque nouvelle base.
REVOKE CONNECT ON DATABASE mlflow  FROM PUBLIC;
REVOKE CONNECT ON DATABASE airflow FROM PUBLIC;
REVOKE CONNECT ON DATABASE eco2mix FROM PUBLIC;
