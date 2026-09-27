import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Gauge

import jwt
from jwt.exceptions import InvalidTokenError
import mlflow.pyfunc
from mlflow.tracking import MlflowClient
import polars as pl
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from scipy.stats import ks_2samp

from src.config.settings import settings
from src.data.create_users import User as DBUser
from src.models.train_model import train, load_feature_frame, select_feature_columns, TARGET
from src.models.predict_model import score, resolve_artifact




MODEL_NAME = "anomalies_conso_national" 
MODEL_ALIAS = "champion"
MODEL_URI = f"models:/{MODEL_NAME}@{MODEL_ALIAS}"

model_state = {
    "model": None,
    "version": "unknown",
    "artifact": None,
    "is_training": False,
}

def load_best_model():
    """Récupère le modèle champion depuis MLflow et met à jour l'état en mémoire."""
    client = MlflowClient()
    try:
        model_version_details = client.get_model_version_by_alias(
            MODEL_NAME, MODEL_ALIAS
        )
        version = str(model_version_details.version)
    except Exception:
        version = "champion"

    loaded_model = mlflow.pyfunc.load_model(MODEL_URI)
    model_state["model"] = loaded_model
    model_state["version"] = version

    artifact_dict = resolve_artifact()
    artifact_dict["model"] = loaded_model
    artifact_dict["version"] = version

    model_state["artifact"] = artifact_dict

def run_training_wrapper():
    """Exécute l'entraînement synchrone existant, puis recharge le modèle."""
    try:
        train() 
        load_best_model()
    finally:
        model_state["is_training"] = False    

# ==============================
# Gestion authentification
# ==============================

SECRET_KEY = "lvcnrM3FcRg5g+RspAYOd8GNA4C4hkrMKuAmNncJ6Vg="
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

def get_users_dict() -> dict[str, dict[str, str]]:
    engine = create_engine(settings.sqlalchemy_url)
    with Session(engine) as session:
        users = session.execute(select(DBUser)).scalars().all()
        return {
            u.username: {
                "username": u.username,
                "password": u.password,
                "role": u.role,
            }
            for u in users
        }

USERS_DB = get_users_dict()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    computed = hmac.new(
        SECRET_KEY.encode("utf-8"),
        plain_password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, hashed_password)

class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str
    role: str

# --- Fonctions et depends Auth ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Jeton d'authentification invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = USERS_DB.get(username)
    if user is None:
        raise credentials_exception
    return User(username=user["username"], role=user["role"])

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Vérifie que l'utilisateur connecté possède les privilèges administrateur."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits administrateur requis pour cette opération"
        )
    return current_user

# ==============================
# Drift monitoring
# ==============================

DATA_DRIFT_KS_PVALUE = Gauge(
    "model_feature_drift_ks_pvalue",
    "P-value du test Kolmogorov-Smirnov par feature (drift si < 0.05)",
    ["feature"],
)
DRIFTED_FEATURES_RATIO = Gauge(
    "model_drifted_features_ratio",
    "Pourcentage de features en dérive statistique",
)
PRED_DRIFT_MEAN = Gauge(
    "model_prediction_mean", "Moyenne glissante des prédictions y_pred"
)

drift_state = {
    "reference_data": None, 
    "live_buffer": [],  
    "buffer_limit": 5, 
}


def load_reference_distribution():
    """Charge un échantillon récent via Polars"""

    feats = load_feature_frame()
    feature_cols = select_feature_columns(feats)
    needed = feature_cols + [TARGET]
    drift_state["reference_data"] = feats.drop_nulls(subset=needed).sort("date_heure")[-500:]

def compute_data_drift():
    """Compare la distribution du buffer live avec la référence"""
    ref_df: pl.DataFrame = drift_state.get("reference_data")
    buffer = drift_state.get("live_buffer")

    if ref_df is None or len(buffer) < 5:
        return

    current_df = pl.DataFrame(buffer)

    features = [
        col
        for col in current_df.columns
        if col in ref_df.columns and col not in ["date_heure", "y_pred"]
    ]

    drifted_count = 0

    for col in features:
        ref_values = ref_df.get_column(col).drop_nulls().to_numpy()
        cur_values = current_df.get_column(col).drop_nulls().to_numpy()

        if len(cur_values) > 0 and len(ref_values) > 0:
            stat, p_value = ks_2samp(ref_values, cur_values)

            DATA_DRIFT_KS_PVALUE.labels(feature=col).set(p_value)

            if p_value < 0.05:
                drifted_count += 1

    if features:
        ratio = (drifted_count / len(features)) * 100
        DRIFTED_FEATURES_RATIO.set(ratio)



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chargement initial du champion au boot de l'API
    try:
        load_best_model()
        load_reference_distribution()
        yield
        model_state.clear()
        drift_state.clear()
    except mlflow.exceptions.MlflowException:
        print('Pas de modèle trouvé : lancer un /train en premier')
        yield

# Lancement app
app = FastAPI(title = "API MLOps - Anomalies réseau", version = "1.0.0", lifespan = lifespan)

# Classes de vérification de formatage des requêtes
class FeatureRow(BaseModel):
    date_heure: str
    prevision_j1: float
    prevision_j: float
    fioul: float
    charbon: float
    gaz: float
    nucleaire: float
    eolien: float
    solaire: float
    hydraulique: float
    pompage: float
    bioenergies: float
    ech_physiques: float
    taux_co2: float
    is_missing: int
    is_imputed: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    doy: int
    is_dst: int
    dow: int
    quarter_of_day: int
    is_weekend: int
    is_holiday: int
    is_school_holiday: int
    is_bridge_day: int
    fourier_day_sin1: float
    fourier_day_cos1: float
    fourier_day_sin2: float
    fourier_day_cos2: float
    fourier_day_sin3: float
    fourier_day_cos3: float
    fourier_week_sin1: float
    fourier_week_cos1: float
    fourier_week_sin2: float
    fourier_week_cos2: float
    fourier_year_sin1: float
    fourier_year_cos1: float
    fourier_year_sin2: float
    fourier_year_cos2: float
    consommation_lag_1d: float
    consommation_lag_7d: float
    consommation_roll_mean_1d: float
    consommation_roll_std_1d: float
    consommation_roll_mean_1w: float
    consommation_roll_std_1w: float
    resid_b1: float
    resid_b2: float

class PredictRequest(BaseModel):
    features: List[FeatureRow]

class PredictionItem(BaseModel):
    date_heure: str
    y_pred: float
    model_version: str

class PredictResponse(BaseModel):
    predictions: List[PredictionItem]


# 0. /token
@app.post("/token", response_model=Token, summary="Obtenir un token JWT")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authentification compatible avec le bouton 'Authorize' de Swagger UI."""
    user = USERS_DB.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]}
    )
    return {"access_token": access_token, "token_type": "bearer"}

# 1. /verify
@app.get('/verify', summary = 'API running')
def get_verify():
    return {"message" : "The API is running"}

# 2. /train
@app.post("/train", status_code=202, summary="Re-train the model", dependencies=[Depends(require_admin)])
def train_endpoint(background_tasks: BackgroundTasks):
    """Launch the training of the model in the background"""
    if model_state["is_training"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un entraînement est déjà en cours d'exécution.",
        )
    model_state["is_training"] = True
    background_tasks.add_task(run_training_wrapper)
    return {
        "status": "Training started in background. Model will hot-reload upon completion."
    }

# 3. /predict
@app.post("/predict", response_model=PredictResponse)
def predict_endpoint(request: PredictRequest, background_tasks: BackgroundTasks):
    """Predicts using the model with the @champion tag"""
    artifact = model_state.get("artifact")
    if artifact is None or artifact.get("model") is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model did not load properly",
        )
    try:
        raw_rows = [row.model_dump() for row in request.features]
        input_data = pl.DataFrame(raw_rows)
        preds = score(feats=input_data, artifact=artifact) 
        mean_pred = float(preds.get_column("y_pred").mean())
        PRED_DRIFT_MEAN.set(mean_pred)
        drift_state["live_buffer"].extend(raw_rows)
        if len(drift_state["live_buffer"]) >= drift_state["buffer_limit"]:
            background_tasks.add_task(compute_data_drift)
            # On conserve une fenêtre glissante (les 5 dernières requêtes)
            drift_state["live_buffer"] = drift_state["live_buffer"][-5:]
        return {"predictions": preds.to_dicts()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'inférence : {str(e)}")


# 4. /reload
@app.post("/reload", status_code=200, summary="Re-load the model", dependencies=[Depends(require_admin)])
def reload_model():
    """Reload the model with the tag @champion"""
    previous_best_model = model_state
    load_best_model()
    new_best_model = model_state
    return {"old_model": f"{MODEL_NAME}"+":"+f"{previous_best_model['version']}", "new_model": f"{MODEL_NAME}"+":"+f"{new_best_model['version']}"}


# Lancement prometheus sur route cible
Instrumentator().instrument(app).expose(app, endpoint="/metrics")