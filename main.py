from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="CRM")

class Customer(BaseModel):
    name: str
    email: str = None
    phone: str = None
    company: str = None

class Deal(BaseModel):
    id: str
    title: str
    amt: float
    status: str = "open"

@app.get("/customers")
def list_customers():
    return (db.table('customers').select('*').execute()).data

@app.post("/customers")
def create_customer(customer: Customer):
    return (db.table('customers').insert(customer.dict()).execute()).data

@app.put("/customers/{id}")
def update_customer(id: int, customer: Customer):
    response = db.table("customers").update(customer.dict()).eq("id", id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return response.data

@app.delete("/customers/{id}")
def delete_customer(id: int):
    response = db.table("customers").delete().eq("id", id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True}
