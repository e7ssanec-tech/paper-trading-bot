from fastapi import FastAPI, Request, HTTPException
import os
import time

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

START_BALANCE = 800.0
BASE_SIZE = 500.0
STEP_SIZE = 20.0

state = {
    "balance": START_BALANCE,
    "equity": START_BALANCE,
    "position": None,
    "entry_price": None,
    "position_size": 0.0,
    "flip_count": 0,
}
