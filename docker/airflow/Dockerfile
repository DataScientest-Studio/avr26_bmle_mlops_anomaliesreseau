FROM apache/airflow:2.10.5-python3.12

# Image volontairement minimale.
#
# On n'installe PAS polars / scikit-learn / statsforecast ici : leurs versions
# entreraient en conflit avec les contraintes d'Airflow. Le calcul lourd tournera
# dans une image applicative séparée, lancée par le DockerOperator.

RUN pip install --no-cache-dir \
        "apache-airflow-providers-docker==3.14.1" \
        "mlflow-skinny==3.16.0"

# Avant `USER airflow` : l'écriture à la racine demande root. Le script déclare
# l'uid courant dans /etc/passwd, que le compose exécute en AIRFLOW_UID pour
# que les dossiers montés restent accessibles à l'utilisateur de l'hôte.
COPY --chmod=0755 docker/airflow/entrypoint.sh /entrypoint.sh

USER airflow

# Remplace l'ENTRYPOINT `airflow` de l'amont ; d'où un CMD complet, et des
# commandes explicites dans le compose (`airflow webserver`, `airflow scheduler`).
ENTRYPOINT ["/entrypoint.sh"]
CMD ["airflow", "webserver"]
