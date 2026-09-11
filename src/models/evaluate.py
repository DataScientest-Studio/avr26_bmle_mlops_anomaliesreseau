"""Vérification du modèle — métriques + figures de contrôle.

Charge l'artefact et les prédictions (ou les recalcule), imprime des métriques
et écrit quatre figures dans ``reports/figures/`` :

1. réel vs prédit sur un mois représentatif ;
2. distribution du résidu + bande de seuil robuste ;
3. score d'anomalie dans le temps, points signalés en rouge ;
4. importance des features (permutation) — top 15.

Usage :
    uv run python -m src.models.evaluate
"""

from __future__ import annotations

import logging

import joblib
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.config.config import settings
from src.models.data_source import load_features_from_csv
from src.models.predict_model import score
from src.models.train_model import MODEL_PATH, TARGET

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate")

FIG_DIR = settings.logs_dir.parent / "reports" / "figures"


def _load_predictions() -> pl.DataFrame:
    """Relit predictions.parquet, ou le recalcule depuis le CSV si absent."""
    pq = settings.data_dir / "processed" / "predictions.parquet"
    if pq.exists():
        return pl.read_parquet(pq)
    logger.info("predictions.parquet absent → recalcul depuis le CSV")
    return score(load_features_from_csv())


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    art = joblib.load(MODEL_PATH)
    pred = _load_predictions().sort("date_heure")

    y_true = pred["y_true"].to_numpy()
    y_pred = pred["y_pred"].to_numpy()
    resid = pred["residual"].to_numpy()

    # --- Métriques -----------------------------------------------------------
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    n_anom = int(pred["is_anomaly"].sum())
    logger.info("MAE=%.1f MW | RMSE=%.1f MW | anomalies=%d/%d (%.2f%%) | version=%s",
                mae, rmse, n_anom, pred.height, 100 * n_anom / pred.height, art["version"])

    p = pred.to_pandas()

    # --- Fig 1 : réel vs prédit (un mois lisible) ----------------------------
    seg = p.iloc[len(p) // 2 : len(p) // 2 + 48 * 30]
    plt.figure(figsize=(12, 4))
    plt.plot(seg["date_heure"], seg["y_true"], lw=0.8, label="réel")
    plt.plot(seg["date_heure"], seg["y_pred"], lw=0.8, alpha=0.8, label="prédit")
    plt.legend(); plt.ylabel("MW"); plt.title("Réel vs prédit (mois représentatif)")
    plt.tight_layout(); plt.savefig(FIG_DIR / "eval_1_reel_vs_predit.png", dpi=110); plt.close()

    # --- Fig 2 : distribution du résidu + seuil ------------------------------
    k, med, scale = art["k"], art["resid_median"], art["resid_scale"]
    plt.figure(figsize=(9, 4))
    plt.hist(resid, bins=120, color="tab:purple", alpha=0.7)
    for s in (-1, 1):
        plt.axvline(med + s * k * scale, color="crimson", ls="--", lw=1)
    plt.title(f"Distribution du résidu — seuil ±{k}·σ̂ (σ̂={scale:.0f} MW)")
    plt.xlabel("résidu (MW)"); plt.tight_layout()
    plt.savefig(FIG_DIR / "eval_2_residu_distribution.png", dpi=110); plt.close()

    # --- Fig 3 : score d'anomalie dans le temps ------------------------------
    plt.figure(figsize=(12, 3.6))
    plt.plot(p["date_heure"], p["anomaly_score"], lw=0.3, color="tab:blue")
    an = p[p["is_anomaly"]]
    plt.scatter(an["date_heure"], an["anomaly_score"], color="red", s=6, zorder=5)
    plt.axhline(k, color="crimson", ls="--", lw=1)
    plt.title(f"Score d'anomalie — {n_anom} points > seuil"); plt.ylabel("score")
    plt.tight_layout(); plt.savefig(FIG_DIR / "eval_3_score_anomalie.png", dpi=110); plt.close()

    # --- Fig 4 : importance des features (permutation, sous-échantillon) ------
    feats = load_features_from_csv()
    cols = art["feature_cols"]
    data = feats.drop_nulls(subset=cols + [TARGET]).sort("date_heure").tail(6000)
    Xv, yv = data.select(cols).to_numpy(), data[TARGET].to_numpy()
    imp = permutation_importance(art["model"], Xv, yv, n_repeats=5, random_state=0,
                                 scoring="neg_mean_absolute_error")
    order = np.argsort(imp.importances_mean)[-15:]
    plt.figure(figsize=(9, 6))
    plt.barh([cols[i] for i in order], imp.importances_mean[order], color="teal")
    plt.title("Importance des features (permutation, top 15)")
    plt.xlabel("Δ MAE si la feature est permutée"); plt.tight_layout()
    plt.savefig(FIG_DIR / "eval_4_importance_features.png", dpi=110); plt.close()

    logger.info("Figures écrites dans %s", FIG_DIR)


if __name__ == "__main__":
    main()
