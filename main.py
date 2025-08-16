from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime
import requests
import csv
from csv import DictReader, DictWriter
import json
import io
from fastapi.responses import Response
from fastapi import File, UploadFile

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="CRM")

class Customer(BaseModel):
    id: str = None
    name: str
    email: str = None
    phone: str = None
    company: str = None

class Deal(BaseModel):
    id: str = None
    title: str
    amt: float
    status: str = "open"

class Note(BaseModel):
    id: str = None
    customer_id: str
    content: str
    type: str = "general"
    created_at: str = None

class Status(BaseModel):
    status: str

@app.get("/customers")
def list_customers():
    return (db.table('customers').select('*').execute()).data

@app.post("/customers")
def create_customer(customer: Customer):
    data = customer.dict(exclude_unset=True)
    data.pop("id", None)  # Remove id if present
    return (db.table('customers').insert(data).execute()).data

@app.put("/customers/{id}")
def update_customer(id: str, customer: Customer):
    data = customer.dict(exclude_unset=True)
    data.pop("id", None)
    resp = db.table("customers").update(data).eq("id", id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return resp.data

@app.delete("/customers/{id}")
def delete_customer(id: str):
    resp = db.table("customers").delete().eq("id", id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True}

@app.get("/customers/{id}")
def get_customer(id: str):
    resp = db.table("customers").select("*").eq("id", id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return resp.data

@app.get("/deals")
def list_deals():
    return (db.table('deals').select('*').execute()).data

@app.post("/deals")
def create_deal(deal: Deal):
    data = deal.dict(exclude_unset=True)
    data.pop("id", None)
    return (db.table('deals').insert(data).execute()).data

@app.put("/deals/{deal_id}")
def update_deal(deal_id: str, deal: Deal):
    data = deal.dict(exclude_unset=True)
    data.pop("id", None)
    resp = db.table("deals").update(data).eq("id", deal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return resp.data

@app.delete("/deals/{deal_id}")
def delete_deal(deal_id: str):
    resp = db.table("deals").delete().eq("id", deal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"ok": True}

@app.get("/deals/{deal_id}")
def get_deal(deal_id: str):
    resp = db.table("deals").select("*").eq("id", deal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return resp.data

@app.post("/users")
def create_user(name: str, email: str, password: str):
    return (db.table("users").insert({"name": name, "email": email, "password": password}).execute()).data

@app.post("/customers/{id}/deals")
def create_customer_deal(id: str, deal: Deal):
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    data = deal.dict(exclude_unset=True)
    data.pop("id", None)
    data["customer_id"] = id
    return (db.table("deals").insert(data).execute()).data

@app.get("/customers/{id}/deals")
def list_customer_deals(id: str):
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return (db.table("deals").select("*").eq("customer_id", id).execute()).data

@app.put("/deals/{deal_id}/status")
def update_deal_status(deal_id: str, status: Status):
    data = status.dict(exclude_unset=True)
    resp = db.table("deals").update(data).eq("id", deal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return resp.data

@app.get("/deals/pipeline")
def get_deals_pipeline():
    deals = (db.table('deals').select('*').execute()).data
    pipeline = {
        "open": [],
        "in_progress": [],
        "won": [],
        "lost": []
    }
    
    for deal in deals:
        stage = deal.get("stage", "open")
        if stage in pipeline:
            pipeline[stage].append(deal)
    
    return pipeline

@app.post("/customers/{id}/notes")
def create_customer_note(id: str, note: Note):
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    data = note.dict(exclude_unset=True)
    data.pop("id", None)
    data["customer_id"] = id
    data["created_at"] = str(datetime.now())
    return (db.table("notes").insert(data).execute()).data

@app.get("/customers/{id}/notes")
def list_customer_notes(id: str):
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return (db.table("notes").select("*").eq("customer_id", id).execute()).data

@app.get("/notes")
def list_notes():
    return (db.table("notes").select("*").execute()).data

@app.delete("/notes/{note_id}")
def delete_note(note_id: str):
    resp = db.table("notes").delete().eq("id", note_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}

@app.get("/analytics/deals-summary")
def get_deals_summary():
    deals = (db.table('deals').select('*').execute()).data
    total = len(deals)
    win = [d for d in deals if d.get('status') == 'win']
    lose = [d for d in deals if d.get('status') == 'lose']
    open = [d for d in deals if d.get('status') in ['open', 'in_progress']]

    total_revenue = sum(d.get('amt', 0) for d in win)
    potential_revenue = sum(d.get('amt', 0) for d in open)

    rate = (len(win) / total * 100) if total > 0 else 0

    return {
        "total_deals": total,
        "won_deals": len(win),
        "lost_deals": len(lose),
        "open_deals": len(open),
        "win_rate_percentage": round(rate, 2),
        "total_revenue": total_revenue,
        "potential_revenue": potential_revenue,
        "average_deal_size": round(total_revenue / len(win), 2) if win else 0
    }

@app.get("/analytics/customer-value/{id}")
def get_customer_value(id: str):
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    deals = (db.table("deals").select("*").eq("customer_id", id).execute()).data
    total = sum(d.get('amt', 0) for d in deals if d.get('status') == 'win')
    potential_value = sum(d.get('amt', 0) for d in deals if d.get('status') in ['open', 'in_progress'])
    tdeals = len(deals)
    wdeals = len([d for d in deals if d.get('status') == 'win'])

    return {
        "customer_id": id,
        "customer_name": customer.data[0].get('name'),
        "total_value": total,
        "potential_value": potential_value,
        "total_deals": tdeals,
        "won_deals": wdeals,
        "average_deal_size": round(total / wdeals, 2) if wdeals > 0 else 0
    }

@app.get("/analytics/top-customers")
def get_top_customers():
    customers = (db.table('customers').select('*').execute()).data
    deals = (db.table('deals').select('*').execute()).data
    leaderboard = []
    for customer in customers:
        customer_deals = [d for d in deals if d.get('customer_id') == customer['id']]
        won_deals = [d for d in customer_deals if d.get('status') == 'win']
        total = sum(d.get('amt', 0) for d in won_deals)
        
        if total > 0:
            leaderboard.append({
                "customer_id": customer['id'],
                "customer_name": customer.get('name'),
                "company": customer.get('company'),
                "email": customer.get('email'),
                "total_revenue": total,
                "deals_count": len(won_deals),
                "average_deal_size": round(total / len(won_deals), 2) if won_deals else 0
            })
    leaderboard.sort(key=lambda x: x['total_revenue'], reverse=True)
    return {
        "top_customers": leaderboard[:10],
        "total_customers_with_revenue": len(leaderboard)
    }

@app.get("/motivation")
def get_motivation():
    r = requests.post("https://ai.hackclub.com/chat/completions", headers={
        "Content-Type": "application/json"
    },
    json={
        "model": "openai/gpt-oss-120b",
        "messages": [
            {
                "role": "user",
                "content": "generate a motivational sales quote or advice in one sentence.... make sure to keep it short, inspiring, and sales-focused."
            }
        ]
    })
    r = r.json()
    return {"quote": r['choices'][0]['message']['content']}

@app.get("/fun-fact")
def get_motivation():
    r = requests.post("https://ai.hackclub.com/chat/completions", headers={
        "Content-Type": "application/json"
    },
    json={
        "model": "openai/gpt-oss-120b",
        "messages": [
            {
                "role": "user",
                "content": "generate a fun fact about sales."
            }
        ]
    })
    r = r.json()
    return {"fun_fact": r['choices'][0]['message']['content']}

@app.get("/export/customers")
def export_customers(format: str = "json"):
    customers = (db.table("customers").select("*").execute()).data
    if not customers:
        return {"error": "No customers found"}
    if format == "csv":
        output = io.StringIO()
        writer = DictWriter(output, fieldnames=customers[0].keys())
        writer.writeheader()
        writer.writerows(customers)
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=customers.csv"})
    else:
        return Response(content=json.dumps(customers, indent=2), media_type="application/json", headers={"Content-Disposition": "attachment; filename=customers.json"})

@app.post("/import/customers")
async def import_customers(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    ext = file.filename.split('.')[-1].lower()
    try:
        content = await file.read()
        if ext == "csv":
            content = content.decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            customers = []
            for row in reader:
                customers.append({
                    "name": row.get("name"),
                    "email": row.get("email"),
                    "company": row.get("company"),
                    "phone": row.get("phone"),
                })
            customers = [c for c in customers if c.get('name')]  # Filter out customers without names
            db.table("customers").insert(customers).execute()
            return {"message": "Customers imported successfully"}
        elif ext == "json":
            content = content.decode("utf-8")
            customers = json.loads(content)
            customers = [c for c in customers if c.get('name')]
            db.table("customers").insert(customers).execute()
            return {"message": "Customers imported successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error processing file")

@app.get("/export/deals")
def export_deals(format: str = "json"):
    deals = (db.table("deals").select("*").execute()).data
    if not deals:
        return {"error": "No deals found"}
    if format == "csv":
        output = io.StringIO()
        writer = DictWriter(output, fieldnames=deals[0].keys())
        writer.writeheader()
        writer.writerows(deals)
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=deals.csv"})
    else:
        return Response(content=json.dumps(deals, indent=2), media_type="application/json", headers={"Content-Disposition": "attachment; filename=deals.json"})

@app.post("/import/deals")
async def import_deals(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    ext = file.filename.split('.')[-1].lower()
    try:
        content = await file.read()
        if ext == "csv":
            content = content.decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            deals = []
            for row in reader:
                deals.append({
                    "name": row.get("name"),
                    "value": row.get("value"),
                    "stage": row.get("stage"),
                    "owner": row.get("owner"),
                })
            deals = [d for d in deals if d.get('name')]
            db.table("deals").insert(deals).execute()
            return {"message": "Deals imported successfully"}
        elif ext == "json":
            content = content.decode("utf-8")
            deals = json.loads(content)
            deals = [d for d in deals if d.get('name')]
            db.table("deals").insert(deals).execute()
            return {"message": "Deals imported successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error processing file")
    
@app.get("/export/notes")
def export_notes(format: str = "json"):
    notes = (db.table("notes").select("*").execute()).data
    if not notes:
        return {"error": "No notes found"}
    if format == "csv":
        output = io.StringIO()
        writer = DictWriter(output, fieldnames=notes[0].keys())
        writer.writeheader()
        writer.writerows(notes)
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=notes.csv"})
    else:
        return Response(content=json.dumps(notes, indent=2), media_type="application/json", headers={"Content-Disposition": "attachment; filename=notes.json"})
    
@app.get("/export/all")
def export_all(format: str = "json"):
    customers = (db.table("customers").select("*").execute()).data
    deals = (db.table("deals").select("*").execute()).data
    notes = (db.table("notes").select("*").execute()).data

    if not (customers or deals or notes):
        return {"error": "No data found"}

    output = io.StringIO()
    if format == "csv":
        writer = DictWriter(output, fieldnames=customers[0].keys())
        writer.writeheader()
        writer.writerows(customers)
        writer = DictWriter(output, fieldnames=deals[0].keys())
        writer.writeheader()
        writer.writerows(deals)
        writer = DictWriter(output, fieldnames=notes[0].keys())
        writer.writeheader()
        writer.writerows(notes)
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=all.csv"})
    else:
        all_data = {
            "customers": customers,
            "deals": deals,
            "notes": notes
        }
        return Response(content=json.dumps(all_data, indent=2), media_type="application/json", headers={"Content-Disposition": "attachment; filename=all.json"})

