FROM apache/airflow:2.10.5-python3.12

# Image volontairement minimale.
#
# On n'installe PAS polars / scikit-learn / statsforecast ici : leurs versions
# entreraient en conflit avec les contraintes d'Airflow. Le calcul lourd tournera
# dans une image applicative séparée, lancée par le DockerOperator.
USER airflow

RUN pip install --no-cache-dir \
        "apache-airflow-providers-docker==3.14.1" \
        "mlflow-skinny==3.16.0"
