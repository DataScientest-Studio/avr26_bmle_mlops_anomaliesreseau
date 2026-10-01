#!/usr/bin/env bash
# Point d'entrée de l'image Airflow.
#
# Le compose démarre les conteneurs en `user: "${AIRFLOW_UID}:0"` pour que les
# fichiers écrits dans les dossiers montés (dags/, logs/, models/) appartiennent
# à l'utilisateur de la machine hôte. Or l'image `apache/airflow` ne connaît que
# `airflow` en uid 50000 : sous un autre uid, `pwd.getpwuid()` échoue et Airflow
# refuse de démarrer avec
#   AirflowConfigException: The user that Airflow is running as has no username
#
# On ajoute donc l'entrée manquante à /etc/passwd, avec le home Airflow comme
# répertoire personnel, puis on lance la commande demandée. Idempotent : sans
# effet si l'uid existe déjà (airflow, root…), et sans effet si /etc/passwd n'est
# pas modifiable — le process part alors avec les identifiants qu'il a, et
# l'échec éventuel reste visible dans les logs.
#
# Ce script REMPLACE l'ENTRYPOINT `airflow` de l'image amont : la commande
# complète est donc passée explicitement (`airflow webserver`, `airflow
# scheduler`, ou `/bin/bash -c …` pour airflow-init). `exec "$@"` ne fait que
# l'exécuter telle quelle.
set -euo pipefail

uid="$(id -u)"

if ! getent passwd "$uid" >/dev/null 2>&1; then
    if printf '%s:x:%s:0:airflow:%s:/bin/bash\n' \
        "$uid" "$uid" "${AIRFLOW_HOME:-/opt/airflow}" >> /etc/passwd 2>/dev/null; then
        echo "[entrypoint] uid ${uid} ajouté à /etc/passwd (home ${AIRFLOW_HOME:-/opt/airflow})" >&2
    else
        echo "[entrypoint] AVERTISSEMENT : uid ${uid} absent de /etc/passwd et /etc/passwd" >&2
        echo "[entrypoint] non modifiable — Airflow peut échouer sur getuser()." >&2
    fi
fi

exec "$@"
