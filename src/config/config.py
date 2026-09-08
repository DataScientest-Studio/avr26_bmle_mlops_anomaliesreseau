"""Configuration du périmètre MODÈLE (pydantic-settings).

Version allégée : pas de base de données ni d'API — on lit la série depuis un
CSV local (le fichier national éCO2mix). Surcharge par variables d'environnement
préfixées ``ANOM_`` ou par un fichier ``.env``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du projet = deux niveaux au-dessus de ce fichier (src/config/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Paramètres du modèle, typés et validés au démarrage."""

    model_config = SettingsConfigDict(
        env_prefix="ANOM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Chemins ----------------------------------------------------------------
    data_dir: Path = REPO_ROOT / "data"
    models_dir: Path = REPO_ROOT / "models"
    logs_dir: Path = REPO_ROOT / "logs"
    # Source de données du modèle : le CSV national téléchargé depuis ODRE.
    raw_csv_path: Path = REPO_ROOT / "data" / "raw" / "eco2mix-national-cons-def.csv"

    # --- Série -------------------------------------------------------------------
    # RTE publie en heure locale France (l'offset est dans la colonne date-heure).
    timezone: str = "Europe/Paris"
    # Cadence de la série. Le national **définitif** (CSV) a un réalisé au pas de
    # 30 min ; le flux temps réel est à 15 min → mettre ANOM_FREQ=15m dans ce cas.
    freq: str = "30m"

    @property
    def freq_minutes(self) -> int:
        """Pas d'échantillonnage en minutes, dérivé de ``freq`` (ex. '30m' → 30)."""
        import re

        m = re.match(r"(\d+)\s*m", self.freq)
        return int(m.group(1)) if m else 15

    @property
    def steps_per_day(self) -> int:
        """Nombre de pas dans une journée (96 à 15 min, 48 à 30 min)."""
        return (24 * 60) // self.freq_minutes

    # --- Calendrier scolaire -----------------------------------------------------
    # Zone de vacances scolaires par défaut (A/B/C). Île-de-France = zone C.
    school_zone: str = Field(default="C", pattern="^[ABC]$")

    def ensure_dirs(self) -> None:
        """Crée les répertoires data/models/logs s'ils n'existent pas."""
        for d in (self.data_dir, self.models_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
