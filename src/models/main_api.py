from fastapi import FastAPI, HTTPException, BackgroundTasks
# from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import List, Optional
from pydantic import BaseModel
import polars as pl
from src.models.predict_model import score
from src.models.train_model import train


# Lancement app
app = FastAPI(title = "API MLOps - Anomalies réseau", version = "1.0.0")
#security = HTTPBasic()

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

# 1. /verify
@app.get('/verify', summary = 'API running')
def get_verify():
    return {"message" : "The API is running"}

# 2. /train
@app.post("/train", status_code=202, summary = 'Re-train the model')
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