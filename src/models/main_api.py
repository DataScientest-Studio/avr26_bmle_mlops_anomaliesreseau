from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, status, Depends, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional
from pydantic import BaseModel
import polars as pl
from src.models.predict_model import score
from src.models.train_model import train
import jwt
from jwt.exceptions import InvalidTokenError

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.data.create_users import User as DBUser
import hashlib
import hmac

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

# Lancement app
app = FastAPI(title = "API MLOps - Anomalies réseau", version = "1.0.0")


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
@app.post("/train", status_code=202, summary = 'Re-train the model', dependencies=[Depends(require_admin)])
def train_endpoint(background_tasks: BackgroundTasks):
    """Launch the training of the model in the background"""
    background_tasks.add_task(train)
    return {"status": "Training started in background"}

# 3. /predict
@app.post("/predict", response_model=PredictResponse)
def predict_endpoint(request: PredictRequest):
    """Predicts """
    try:
        input_data = pl.DataFrame([row.model_dump() for row in request.features])
        preds = score(feats=input_data)
        return {"predictions": preds.to_dicts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'inférence : {str(e)}")