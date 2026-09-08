from fastapi import FastAPI, HTTPException, BackgroundTasks
# from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import List, Optional
from pydantic import BaseModel
from src.models.predict_model import predict
from src.models.train_model import train


# Lancement app
app = FastAPI(title = "API MLOps - Anomalies réseau", version = "1.0.0")
#security = HTTPBasic()

# Classes de vérification de formatage des requêtes
class PredictRequest(BaseModel):
    features: List[List[float]]

class PredictResponse(BaseModel):
    predictions: List[int]

# 1. /verify
@app.get('/verify', summary = 'API running')
def get_verify():
    return {"message" : "The API is running"}

# 2. /train
@app.post("/train", status_code=202)
def train_endpoint(background_tasks: BackgroundTasks):
    """Launch the training of the model in the background"""
    background_tasks.add_task(train)
    return {"status": "Training started in background"}

# 3. /predict
@app.post("/predict", response_model=PredictResponse)
def predict_endpoint(request: PredictRequest):
    """Predicts """
    try:
        preds = predict(request.features)
        return {"predictions": preds}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'inférence : {str(e)}")



