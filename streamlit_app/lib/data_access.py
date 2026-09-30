"""SEUL point d'accès aux données de l'app de démo.

Règles :
- les pages n'importent jamais ``src.*`` : elles passent par ce module ;
- ``src.*`` est importé PARESSEUSEMENT (dans les fonctions), pour que l'app
  démarre même si une dépendance ou un service manque ;
- chaque fonction publique renvoie ``(donnee, erreur)`` : ``(obj, None)`` si OK,
  ``(None, "message")`` si un service est éteint — jamais d'exception vers la page ;
- les petites agrégations se font ici, côté polars (API lazy), AVANT
  ``.to_pandas()`` dans les pages.

Source des données, variable ``ANOM_APP_SOURCE`` :
- ``direct`` (défaut) : réutilise ``src.*`` + PostgreSQL + MLflow ;
- ``api`` : passerait par l'API FastAPI — squelette ``_via_api`` non implémenté.
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl
import streamlit as st
from dotenv import load_dotenv

# --- Racine du repo dans sys.path (streamlit_app/lib/data_access.py -> parents[2])
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

APP_SOURCE = os.environ.get("ANOM_APP_SOURCE", "direct").strip().lower()
API_URL = os.environ.get("ANOM_API_URL", "http://localhost:8000")

# MLflow : pas de retries longs quand le serveur est éteint (sinon la page gèle).
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")

Result = tuple[Any, str | None]


def _load_dotenv() -> None:
    """Charge ``REPO_ROOT/.env`` dans l'environnement (sans écraser l'existant).

    pydantic-settings lit ``.env`` relativement au dossier courant : on le
    pré-charge pour que l'app marche qu'on la lance depuis la racine ou depuis
    ``streamlit_app/``.

    On délègue le parsing à ``python-dotenv`` — la bibliothèque que
    pydantic-settings utilise elle-même pour ``.env`` — sinon les deux lectures
    divergent. Un parseur artisanal ignorait les commentaires en fin de ligne :
    ``POSTGRES_HOST=localhost   # depuis l'hôte`` devenait un nom d'hôte de
    quarante caractères, et le DSN produit était rejeté par psycopg. Comme
    ``os.environ`` prime sur le fichier ``.env``, c'est cette valeur empoisonnée
    qui l'emportait et ``src.config.settings`` ne la voyait jamais.
    """
    env = REPO_ROOT / ".env"
    if not env.is_file():
        return
    # .env illisible : les pages dégraderont plus bas, mieux vaut ne pas planter ici.
    with suppress(Exception):
        load_dotenv(env, override=False)


_load_dotenv()


def _msg(what: str, exc: BaseException) -> str:
    return f"{what} — {type(exc).__name__} : {exc}"


# =============================================================================
# Mode API (squelette, non implémenté)
# =============================================================================
def _via_api(endpoint: str, **params: Any) -> Any:
    """Squelette du mode ``ANOM_APP_SOURCE=api``.

    À implémenter quand l'API exposera des routes de lecture, par ex. :
      GET {API_URL}/features?limit=…      -> table de features
      GET {API_URL}/scores?start=…&end=…  -> date_heure, y_true, y_pred, …
      GET {API_URL}/model/champion        -> métadonnées du champion
    (httpx est déjà dans les dépendances ; penser au token JWT de /token.)
    """
    raise NotImplementedError(
        f"Mode ANOM_APP_SOURCE=api non implémenté (endpoint '{endpoint}'). "
        "Repasser en ANOM_APP_SOURCE=direct."
    )


def _api_guard(endpoint: str) -> str | None:
    """Renvoie un message d'erreur si on est en mode api (non implémenté)."""
    if APP_SOURCE == "direct":
        return None
    if APP_SOURCE != "api":
        return f"ANOM_APP_SOURCE='{APP_SOURCE}' inconnu (attendu : direct | api)."
    try:
        _via_api(endpoint)
    except NotImplementedError as exc:
        return str(exc)
    return None


# =============================================================================
# Configuration / état des services
# =============================================================================
def get_settings() -> Result:
    """Paramètres modèle/MLflow du projet (``src.config.config.settings``)."""
    try:
        from src.config.config import settings

        return settings, None
    except Exception as exc:
        return None, _msg("Configuration src.config.config illisible", exc)


# Noms d'hôte du réseau Docker Compose : port à l'intérieur du conteneur, et nom
# de la variable d'environnement qui porte le port publié sur l'hôte.
_DOCKER_SERVICE_PORTS = {
    "mlflow": ("5000", "MLFLOW_PORT"),
    "api": ("8000", "API_PORT"),
    "prometheus": ("9090", "PROMETHEUS_PORT"),
    "grafana": ("3000", "GRAFANA_PORT"),
    "airflow": ("8080", "AIRFLOW_PORT"),
}


def _in_container() -> bool:
    """Vrai si ce process tourne dans un conteneur."""
    return Path("/.dockerenv").exists()


def _host_reachable(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True


def to_host_url(url: str) -> str:
    """Réécrit un nom de service Docker en ``localhost`` quand on tourne sur l'hôte.

    ``.env`` porte l'URI que les *conteneurs* utilisent (``http://mlflow:5000``),
    alors que l'app Streamlit tourne sur la machine de l'hôte, où ce nom ne
    résout pas. Sans cette réécriture, les pages MLflow affichent « serveur
    injoignable » alors qu'il tourne. La résolution DNS décide : si le nom
    résout (réseau Compose), on n'y touche pas.
    """
    if _in_container():
        return url
    m = re.match(r"^(?P<scheme>https?://)(?P<host>[^/:]+)(?P<rest>[:/].*)?$", url.strip())
    if not m:
        return url
    host, rest = m["host"], m["rest"] or ""
    if host == "localhost" or _host_reachable(host):
        return url
    entry = _DOCKER_SERVICE_PORTS.get(host)
    if entry is None:
        return url
    internal_port, env_var = entry
    # Le port interne du conteneur et celui publié sur l'hôte diffèrent
    # (MLFLOW_PORT…). On remplace le port d'origine par le port publié.
    port = re.match(r"^:(\d+)(?P<tail>.*)$", rest)
    tail = port["tail"] if port else rest
    return f"{m['scheme']}localhost:{os.environ.get(env_var, internal_port)}{tail}"


def mlflow_uri() -> str:
    """URI MLflow utilisable depuis l'hôte : ``MLFLOW_TRACKING_URI``, config, défaut.

    L'URI de ``.env`` vise le réseau Docker ; on la réécrit donc en ``localhost``
    quand elle n'est pas résolvable d'ici (voir :func:`to_host_url`).
    """
    uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if not uri:
        settings, _ = get_settings()
        uri = (getattr(settings, "mlflow_tracking_uri", "") or "").strip()
    if not uri:
        uri = f"http://localhost:{os.environ.get('MLFLOW_PORT', '5000')}"
    return to_host_url(uri)


def mlflow_ui_url() -> str:
    """URL de l'UI MLflow pour le navigateur (surcharge : ``MLFLOW_UI_URL``)."""
    return to_host_url(os.environ.get("MLFLOW_UI_URL", "").strip() or mlflow_uri())


def _http_ok(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return 200 <= resp.status < 400, f"HTTP {resp.status}"
    except Exception as exc:
        return False, type(exc).__name__


def _db_ok() -> tuple[bool, str]:
    try:
        import psycopg

        from src.config.settings import settings as db_settings

        with psycopg.connect(db_settings.dsn, connect_timeout=2) as conn:
            version = conn.execute("SHOW server_version").fetchone()[0]
        return True, f"PostgreSQL {version}"
    except Exception as exc:
        return False, f"{type(exc).__name__} : {str(exc)[:120]}"


def service_urls() -> dict[str, str]:
    """URL navigateur de chaque service (surcharge par variables d'environnement).

    Ports du docker-compose : api 8000, mlflow ${MLFLOW_PORT:-5000}, silo console
    9001 (liée à 127.0.0.1 ; l'API S3 9000 reste interne au réseau Docker),
    airflow ${AIRFLOW_PORT:-8080}, prometheus 9090, grafana 3000.
    """
    env = os.environ.get
    urls = {
        "api": env("ANOM_API_URL", API_URL),
        "mlflow": mlflow_ui_url(),
        "silo": env("ANOM_SILO_URL", "http://localhost:9001"),
        "airflow": env("ANOM_AIRFLOW_URL", f"http://localhost:{env('AIRFLOW_PORT', '8080')}"),
        "prometheus": env("ANOM_PROMETHEUS_URL", "http://localhost:9090"),
        "grafana": env("ANOM_GRAFANA_URL", "http://localhost:3000"),
    }
    # Une URL de service peut venir de .env avec un nom de réseau Docker.
    return {name: to_host_url(url) for name, url in urls.items()}


# (nom, rôle, chemin de santé) — sondes HTTP informatives.
_HTTP_SERVICES = [
    ("api", "FastAPI — /token, /predict, /train, /reload, /metrics", "/verify"),
    ("silo", "Stockage S3 des artefacts MLflow (console)", "/"),
    ("airflow", "Orchestration — DAG retrain_eco2mix", "/health"),
    ("prometheus", "Collecte des métriques (scrape /metrics)", "/-/healthy"),
    ("grafana", "Tableaux de bord", "/api/health"),
]


@st.cache_data(ttl=15, show_spinner=False)
def get_services_status() -> list[dict]:
    """État des services docker-compose (toujours une liste, jamais d'exception).

    db et mlflow sont vérifiés en priorité (utiles à la démo) ; les autres sont
    des sondes HTTP informatives.
    """
    rows = []
    ok, detail = _db_ok()
    rows.append({"service": "db", "role": "PostgreSQL — données + backend MLflow",
                 "ok": ok, "detail": detail, "essentiel": True})
    ok, detail = _http_ok(mlflow_uri().rstrip("/") + "/health")
    rows.append({"service": "mlflow", "role": "Tracking + Model Registry",
                 "ok": ok, "detail": f"{mlflow_uri()} · {detail}", "essentiel": True})
    urls = service_urls()
    for name, role, path in _HTTP_SERVICES:
        ok, detail = _http_ok(urls[name].rstrip("/") + path, timeout=1.0)
        rows.append({"service": name, "role": role, "ok": ok, "detail": detail,
                     "essentiel": False})
    return rows


# =============================================================================
# Contrat de l'API FastAPI (lu dans /openapi.json)
# =============================================================================
_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


@st.cache_data(ttl=15, show_spinner=False)
def _openapi_cached(url: str) -> list[dict]:
    with urllib.request.urlopen(f"{url.rstrip('/')}/openapi.json", timeout=3) as resp:  # noqa: S310
        spec = json.loads(resp.read().decode("utf-8"))
    rows = []
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method.lower() not in _METHODS or not isinstance(op, dict):
                continue
            rows.append({
                "method": method.upper(),
                "path": path,
                "summary": op.get("summary") or op.get("operationId") or "—",
                "secured": bool(op.get("security")),
            })
    order = {m: i for i, m in enumerate(m for m in _METHODS)}
    rows.sort(key=lambda r: (r["path"], order.get(r["method"].lower(), 99)))
    return rows


def get_api_routes() -> Result:
    """Routes réellement exposées par l'API : ``(liste, None)`` ou ``(None, msg)``.

    Le plan de la page doit correspondre à ce que l'API sert *vraiment* : la
    lecture de ``/openapi.json`` évite qu'une route soit annoncée et disparaisse.
    """
    url = service_urls()["api"]
    try:
        rows = _openapi_cached(url)
    except Exception as exc:
        return None, _msg(f"Contrat de l'API '{url}/openapi.json' illisible", exc)
    if not rows:
        return None, "L'API ne déclare aucune route."
    return rows, None


# =============================================================================
# Prometheus (requête instantanée sur /api/v1/query)
# =============================================================================
@st.cache_data(ttl=15, show_spinner=False)
def _prom_cached(url: str, expr: str) -> list[dict]:
    q = urllib.parse.urlencode({"query": expr})  # noqa: S310
    with urllib.request.urlopen(f"{url.rstrip('/')}/api/v1/query?{q}", timeout=3) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("error", "réponse Prometheus inattendue"))
    out = []
    for s in payload.get("data", {}).get("result", []):
        ts, val = s.get("value", [None, None])
        out.append({"labels": {k: v for k, v in (s.get("metric") or {}).items()
                               if not k.startswith("__")},
                    "ts": ts, "value": float(val) if val is not None else None})
    return out


def get_prom_query(expr: str) -> Result:
    """Instant vectorielle pour une expression PromQL.

    Vérifie d'abord que la cible est *scrapee* (``up == 1``) : sans cela une
    expression qui ne retourne rien est ambiguë — soit Prometheus est éteint,
    soit la métrique n'a jamais été produite.
    """
    url = service_urls()["prometheus"]
    try:
        up = _prom_cached(url, "up")
    except Exception as exc:
        return None, _msg(f"Prometheus '{url}' injoignable", exc)
    if not up or not up[0]["value"]:
        return None, f"Prometheus '{url}' ne renvoie aucune cible."
    if up[0]["value"] == 0:
        job = up[0]["labels"].get("job", "?")
        return None, (f"Prometheus ne scrape pas la cible `{job}` "
                      f"(API injoignable ou `/metrics` en erreur).")
    try:
        rows = _prom_cached(url, expr)
    except Exception as exc:
        return None, _msg(f"Requête PromQL impossible ({expr})", exc)
    return rows, None


def get_prom_scalar(expr: str) -> Result:
    """Raccourci : première valeur d'une expression, ou ``(None, msg)``."""
    rows, err = get_prom_query(expr)
    if err:
        return None, err
    return (rows[0]["value"] if rows else None), None


# =============================================================================
# Features (src.models.data_source.load_features)
# =============================================================================
@st.cache_data(ttl=600, show_spinner="Chargement des features…")
def _features_cached() -> pl.DataFrame:
    from src.models.data_source import load_features

    return load_features()


def get_features() -> Result:
    """Table de features complète (polars) — ``(df, None)`` ou ``(None, msg)``."""
    if err := _api_guard("features"):
        return None, err
    try:
        df = _features_cached()
    except Exception as exc:
        source = os.environ.get("ANOM_SOURCE", "db")
        return None, _msg(f"Chargement des features impossible (ANOM_SOURCE={source})", exc)
    if df is None or df.height == 0:
        return None, "La table de features est vide."
    return df, None


def get_features_summary() -> Result:
    """Métadonnées de la table : lignes, période, familles de colonnes."""
    df, err = get_features()
    if err:
        return None, err
    cols = df.columns
    fourier = [c for c in cols if any(t in c.lower() for t in ("sin", "cos", "fourier"))]
    lags = [c for c in cols if "lag" in c.lower() or "roll" in c.lower()]
    calendar = [c for c in ("hour", "dow", "doy", "month", "year", "quarter_of_day",
                            "is_weekend", "is_holiday", "is_school_holiday",
                            "is_bridge_day", "is_dst", "off") if c in cols]
    dmin, dmax = df.select(pl.col("date_heure").min().alias("dmin"),
                           pl.col("date_heure").max().alias("dmax")).row(0)
    return {
        "n_rows": df.height,
        "n_cols": df.width,
        "date_min": dmin,
        "date_max": dmax,
        "calendar": calendar,
        "fourier": fourier,
        "lags": lags,
        "source": os.environ.get("ANOM_SOURCE", "db"),
    }, None


def get_features_head(n: int = 10) -> Result:
    df, err = get_features()
    if err:
        return None, err
    return df.sort("date_heure", descending=True).head(n), None


def get_calendar_profile() -> Result:
    """Conso moyenne par heure × (ouvré / chômé) — 48 lignes max."""
    df, err = get_features()
    if err:
        return None, err
    try:
        off = pl.col("off") if "off" in df.columns else (
            pl.col("is_weekend").cast(pl.Boolean) | pl.col("is_holiday").cast(pl.Boolean)
        )
        prof = (
            df.lazy()
            .select("hour", "consommation", off.cast(pl.Boolean).alias("off"))
            .drop_nulls()
            .group_by("hour", "off")
            .agg(pl.col("consommation").mean().alias("conso_moy"),
                 pl.len().alias("n"))
            .with_columns(pl.when(pl.col("off")).then(pl.lit("Week-end / férié"))
                          .otherwise(pl.lit("Jour ouvré")).alias("type_jour"))
            .sort("off", "hour")
            .collect()
        )
        return prof, None
    except Exception as exc:
        return None, _msg("Agrégation calendrier impossible", exc)


def get_dow_profile() -> Result:
    """Conso moyenne par jour de semaine (7 lignes)."""
    df, err = get_features()
    if err:
        return None, err
    try:
        prof = (
            df.lazy()
            .group_by("dow")
            .agg(pl.col("consommation").mean().alias("conso_moy"))
            .sort("dow")
            .collect()
        )
        return prof, None
    except Exception as exc:
        return None, _msg("Agrégation jour de semaine impossible", exc)


# =============================================================================
# Modèle : artefact (champion MLflow ou joblib) + scoring
# =============================================================================
@st.cache_resource(ttl=600, show_spinner="Chargement du modèle (champion MLflow)…")
def _artifact_cached() -> dict:
    from src.models.predict_model import resolve_artifact

    return resolve_artifact()


def get_artifact() -> Result:
    """Artefact du modèle (dict) : champion MLflow, repli ``models/model.joblib``."""
    if err := _api_guard("model/champion"):
        return None, err
    try:
        return _artifact_cached(), None
    except Exception as exc:
        return None, _msg("Aucun modèle chargeable (ni champion MLflow ni models/model.joblib)", exc)


def get_artifact_info() -> Result:
    """Vue sérialisable de l'artefact (sans l'objet modèle)."""
    art, err = get_artifact()
    if err:
        return None, err
    meta = art.get("metadata") or {}
    return {
        "version": art.get("version"),
        "kind": art.get("kind"),
        "target": art.get("target"),
        "k": float(art.get("k", 3.0)),
        "resid_median": float(art.get("resid_median", 0.0)),
        "resid_scale": float(art.get("resid_scale", 1.0)),
        "n_features": len(art.get("feature_cols") or []),
        "origine": "MLflow (champion)" if "mlflow_version" in meta else "models/model.joblib",
        "metadata": {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))},
    }, None


@st.cache_data(ttl=600, show_spinner="Scoring de la série…")
def _scores_cached(version: str) -> pl.DataFrame:  # `version` = clé de cache
    from src.models.predict_model import score

    return score(_features_cached(), _artifact_cached()).sort("date_heure")


def get_scores() -> Result:
    """Série scorée complète : date_heure, y_true, y_pred, residual, anomaly_score, …"""
    art, err = get_artifact()
    if err:
        return None, err
    _, err = get_features()
    if err:
        return None, err
    try:
        df = _scores_cached(str(art.get("version")))
    except Exception as exc:
        return None, _msg("Scoring impossible", exc)
    if "y_true" not in df.columns:
        return None, "La cible est absente : scoring sans vérité terrain, pas d'anomalies calculables."
    return df, None


def get_score_window(end, days: int, k: float) -> Result:
    """Fenêtre de ``days`` jours se terminant à ``end`` ; is_anomaly recalculé à k.

    Filtrage + recalcul côté polars (lazy) → petite table prête pour Altair.
    """
    df, err = get_scores()
    if err:
        return None, err
    try:
        tz = getattr(df.schema["date_heure"], "time_zone", None)
        end_dt = datetime.combine(end, dtime.min) + timedelta(days=1)
        if tz:
            end_dt = end_dt.replace(tzinfo=ZoneInfo(tz))
        start_dt = end_dt - timedelta(days=days)
        win = (
            df.lazy()
            .filter(pl.col("date_heure").is_between(start_dt, end_dt, closed="left"))
            .with_columns((pl.col("anomaly_score") > k).alias("is_anomaly"))
            .collect()
        )
        # Pour l'affichage (Altair / Vega) : heure locale naïve.
        if tz:
            win = win.with_columns(pl.col("date_heure").dt.replace_time_zone(None))
        return win, None
    except Exception as exc:
        return None, _msg("Filtrage de la fenêtre impossible", exc)


def get_anomaly_counts(k_values: list[float]) -> Result:
    """Nombre d'anomalies sur toute la série pour chaque seuil k (courbe de choix de k)."""
    df, err = get_scores()
    if err:
        return None, err
    s = df.lazy().select("anomaly_score")
    out = s.select([(pl.col("anomaly_score") > k).sum().alias(f"{i}")
                    for i, k in enumerate(k_values)]).collect().row(0)
    return pl.DataFrame({"k": k_values, "n_anomalies": list(out)}), None


def get_top_anomalies(k: float, n: int = 15) -> Result:
    """Les n anomalies les plus fortes sur toute la série (pour naviguer)."""
    df, err = get_scores()
    if err:
        return None, err
    top = (df.lazy().filter(pl.col("anomaly_score") > k)
           .sort("anomaly_score", descending=True).head(n)
           .select("date_heure", "y_true", "y_pred", "residual", "anomaly_score")
           .collect())
    return top, None


# =============================================================================
# MLflow : runs, registry, champion
# =============================================================================
def _mlflow_ready() -> str | None:
    """Pré-vérification rapide (évite les timeouts du client MLflow)."""
    ok, detail = _http_ok(mlflow_uri().rstrip("/") + "/health")
    if not ok:
        return (f"Serveur MLflow injoignable ({mlflow_uri()} · {detail}). "
                "Lancer `docker compose up -d mlflow` et exporter MLFLOW_TRACKING_URI.")
    return None


def _mlflow_names() -> tuple[str, str, str]:
    settings, _ = get_settings()
    return (
        getattr(settings, "mlflow_experiment", "anomalies_conso"),
        getattr(settings, "mlflow_model_name", "anomalies_conso_national"),
        getattr(settings, "mlflow_champion_alias", "champion"),
    )


@st.cache_resource(show_spinner=False)
def _mlflow_client(uri: str):
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(uri)
    return MlflowClient(tracking_uri=uri)


@st.cache_data(ttl=30, show_spinner="Lecture des runs MLflow…")
def _runs_cached(uri: str, experiment: str) -> pl.DataFrame:
    import mlflow

    client = _mlflow_client(uri)
    exp = client.get_experiment_by_name(experiment)
    if exp is None:
        raise LookupError(f"Expérience MLflow '{experiment}' introuvable — lancer `make train`.")
    runs = mlflow.search_runs(experiment_ids=[exp.experiment_id],
                              order_by=["attributes.start_time ASC"])
    if runs.empty:
        return pl.DataFrame()
    wanted = {
        "run_id": "run_id",
        "tags.mlflow.runName": "run_name",
        "start_time": "start_time",
        "status": "status",
        "params.git_commit": "git_commit",
        "params.data_hash": "data_hash",
        "params.n_rows": "n_rows",
        "params.k": "k",
        "params.kind": "kind",
        "metrics.mae_valid": "mae_valid",
        "tags.date_min": "date_min",
        "tags.date_max": "date_max",
    }
    keep = {src: dst for src, dst in wanted.items() if src in runs.columns}
    pdf = runs[list(keep)].rename(columns=keep)
    if "start_time" in pdf.columns and getattr(pdf["start_time"].dt, "tz", None) is not None:
        pdf["start_time"] = pdf["start_time"].dt.tz_convert(None)
    df = pl.from_pandas(pdf)
    for col in ("git_commit", "data_hash", "run_name", "kind"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(col))
    if "mae_valid" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("mae_valid"))
    return df.with_row_index("run_no", offset=1)


def get_mlflow_runs() -> Result:
    """Runs de l'expérience : run_id, git_commit, data_hash, n_rows, k, mae_valid, …"""
    if err := _mlflow_ready():
        return None, err
    exp, _, _ = _mlflow_names()
    try:
        df = _runs_cached(mlflow_uri(), exp)
    except Exception as exc:
        return None, _msg("Lecture des runs MLflow impossible", exc)
    if df.height == 0:
        return None, f"Aucun run dans l'expérience '{exp}' — lancer `make train`."
    return df, None


@st.cache_data(ttl=30, show_spinner="Lecture du Model Registry…")
def _registry_cached(uri: str, name: str, alias: str) -> tuple[pl.DataFrame, dict | None]:
    client = _mlflow_client(uri)
    versions = client.search_model_versions(f"name='{name}'")
    champ = None
    try:
        mv = client.get_model_version_by_alias(name, alias)
        champ = {"version": str(mv.version), "run_id": mv.run_id,
                 "created": time.strftime("%Y-%m-%d %H:%M",
                                          time.localtime(mv.creation_timestamp / 1000))}
    except Exception:
        champ = None
    rows = [{
        "version": int(v.version),
        "run_id": v.run_id,
        "status": v.status,
        "aliases": ", ".join(getattr(v, "aliases", []) or []),
        "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(v.creation_timestamp / 1000)),
        "is_champion": champ is not None and str(v.version) == champ["version"],
    } for v in versions]
    df = pl.DataFrame(rows) if rows else pl.DataFrame()
    if df.height:
        df = df.sort("version", descending=True)
    return df, champ


def get_registry() -> Result:
    """``((versions_df, champion_dict|None), None)`` ou ``(None, msg)``."""
    if err := _mlflow_ready():
        return None, err
    _, name, alias = _mlflow_names()
    try:
        versions, champ = _registry_cached(mlflow_uri(), name, alias)
    except Exception as exc:
        return None, _msg(f"Lecture du registry '{name}' impossible", exc)
    if versions.height == 0:
        return None, f"Aucune version enregistrée pour le modèle '{name}'."
    return (versions, champ), None


def get_names() -> dict:
    exp, name, alias = _mlflow_names()
    return {"experiment": exp, "model_name": name, "alias": alias,
            "uri": mlflow_uri(), "ui": mlflow_ui_url(), "app_source": APP_SOURCE}


def clear_caches() -> None:
    st.cache_data.clear()
    st.cache_resource.clear()


# =============================================================================
# Base de données : volumétrie par couche, cloisonnement, snapshots
# =============================================================================
DB_LAYERS = ("staging", "raw", "clean")


@st.cache_data(ttl=30, show_spinner=False)
def _db_overview_cached() -> dict:
    import psycopg

    from src.config.settings import settings as db_settings

    # autocommit : une requête en échec (alembic_version absente) n'annule pas les autres.
    with psycopg.connect(db_settings.dsn, connect_timeout=3, autocommit=True) as conn:
        tables = conn.execute(
            """
            SELECT schemaname, relname, n_live_tup, pg_total_relation_size(relid)
            FROM pg_stat_user_tables
            WHERE schemaname = ANY(%s)
            ORDER BY schemaname, relname
            """,
            (list(DB_LAYERS),),
        ).fetchall()
        databases = conn.execute(
            """
            SELECT datname, pg_get_userbyid(datdba)
            FROM pg_database
            WHERE NOT datistemplate AND datname <> 'postgres'
            ORDER BY datname
            """
        ).fetchall()
        alembic = None
        with suppress(Exception):
            alembic = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return {
        "tables": [{"couche": s, "table": t, "lignes": int(n), "taille_mo": round(b / 1e6, 1)}
                   for s, t, n, b in tables],
        "databases": [{"base": d, "propriétaire": o} for d, o in databases],
        "alembic": alembic,
    }


def get_db_overview() -> Result:
    """Volumétrie par couche (statistiques PostgreSQL), bases et propriétaires, révision Alembic."""
    try:
        return _db_overview_cached(), None
    except Exception as exc:
        return None, _msg("Base PostgreSQL injoignable", exc)


def get_snapshots() -> Result:
    """Snapshots parquet figés par ``make snapshot`` (dossier : ``ANOM_SNAPSHOT_DIR``)."""
    folder = Path(os.environ.get("ANOM_SNAPSHOT_DIR", REPO_ROOT / "data" / "snapshots"))
    if not folder.is_absolute():
        folder = REPO_ROOT / folder
    files = sorted(folder.glob("**/*.parquet"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        shown = folder.relative_to(REPO_ROOT) if folder.is_relative_to(REPO_ROOT) else folder
        return None, f"Aucun snapshot dans `{shown}` — lancer `make snapshot`."
    rows = []
    for f in files[:10]:
        n = None
        with suppress(Exception):
            n = pl.scan_parquet(f).select(pl.len()).collect().item()
        rows.append({
            "snapshot": f.name,
            "créé le": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "lignes": n,
            "taille (Mo)": round(f.stat().st_size / 1e6, 1),
        })
    return rows, None


# =============================================================================
# Airflow : derniers runs du DAG (API REST) + curseur d'arrivée des données
# =============================================================================
AIRFLOW_DAG_ID = os.environ.get("ANOM_AIRFLOW_DAG", "retrain_eco2mix")
_PARIS = ZoneInfo("Europe/Paris")


def _fmt_ts(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(_PARIS).strftime("%Y-%m-%d %H:%M")


@st.cache_data(ttl=15, show_spinner=False)
def _airflow_runs_cached(url: str, dag_id: str, limit: int) -> list[dict]:
    # Identifiants lus ici plutôt que passés en argument : ils n'entrent pas dans la clé de cache.
    user = os.environ.get("AIRFLOW_ADMIN_USER", "admin")
    pwd = os.environ.get("AIRFLOW_ADMIN_PASSWORD", "admin")
    q = urllib.parse.urlencode({"order_by": "-execution_date", "limit": limit})
    req = urllib.request.Request(f"{url.rstrip('/')}/api/v1/dags/{dag_id}/dagRuns?{q}")  # noqa: S310
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode())
    with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    rows = []
    for r in payload.get("dag_runs", []):
        start, end = r.get("start_date"), r.get("end_date")
        duration = None
        if start and end:
            duration = round((datetime.fromisoformat(end)
                              - datetime.fromisoformat(start)).total_seconds())
        rows.append({"state": r.get("state"), "run_type": r.get("run_type"),
                     "start": _fmt_ts(start), "duration_s": duration})
    return rows


def get_airflow_runs(limit: int = 5) -> Result:
    """Derniers runs du DAG : ``(liste, None)`` ou ``(None, msg)``."""
    url = service_urls()["airflow"]
    try:
        rows = _airflow_runs_cached(url, AIRFLOW_DAG_ID, limit)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return None, ("Airflow refuse l'authentification : activer `basic_auth` "
                          "(AIRFLOW__API__AUTH_BACKENDS) et renseigner AIRFLOW_ADMIN_USER / "
                          "AIRFLOW_ADMIN_PASSWORD dans `.env`.")
        if exc.code == 404:
            return None, f"DAG `{AIRFLOW_DAG_ID}` introuvable dans Airflow."
        return None, _msg(f"API Airflow '{url}' en erreur", exc)
    except Exception as exc:
        return None, _msg(f"Airflow '{url}' injoignable", exc)
    if not rows:
        return None, f"Aucun run pour `{AIRFLOW_DAG_ID}` — le DAG est peut-être encore en pause."
    return rows, None


def get_max_year() -> Result:
    """Valeur du curseur ``src/data/max_year.conf`` (dernière année « arrivée »)."""
    path = REPO_ROOT / "src" / "data" / "max_year.conf"
    try:
        return path.read_text(encoding="utf-8").strip(), None
    except Exception as exc:
        return None, _msg("Curseur max_year.conf illisible", exc)
