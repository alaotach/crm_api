from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
import csv
from csv import DictWriter
import json
import io
from fastapi.responses import Response
from fastapi import File, UploadFile
import jwt
import hashlib
import secrets
import base64
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
JWT_KEY = os.getenv('JWT_KEY')
JWT_ALGO = 'HS256'
JWT_EXPIRE = 1800

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="CRM")
security = HTTPBearer()

def create_jwt_token(data: dict) -> str:
    payload = {
        **data,
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXPIRE)
    }
    token = jwt.encode(payload, JWT_KEY, algorithm=JWT_ALGO)
    return token

def custom_hash_password(password: str, salt: str = None) -> tuple:
    if salt is None:
        salt = secrets.token_hex(32)
    salted = password + salt
    for _ in range(6969):
        salted = hashlib.sha256(salted.encode()).hexdigest()

    return salted, salt

def log_audit_event(
    user_id: str = None,
    action: str = None,
    type: str = None,
    resource_id: str = None,
    details: str = None,
    ip: str = None,
    agent: str = None
):
    try:
        audit_data = {
            "user_id": user_id,
            "action": action,
            "type": type,
            "resource_id": resource_id,
            "details": details,
            "ip": ip,
            "agent": agent,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        db.table("audit_logs").insert(audit_data).execute()
    except Exception as e:
        print(f"Audit logging failed: {str(e)}")

def get_client_info(request: Request):
    ip = request.client.host if request.client else None
    agent = request.headers.get("user-agent")
    return ip, agent

def verify(password, hashed, salt):
    test_hash, _ = custom_hash_password(password, salt)
    return test_hash == hashed

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_KEY, algorithms=[JWT_ALGO])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
def get_current_user(user_id: str = Depends(verify_token)):
    user = db.table("users").select("*").eq("id", user_id).execute()
    if not user.data:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )
    return user.data[0]

class Customer(BaseModel):
    id: str = None
    name: str
    email: str = None
    phone: str = None
    company: str = None
    assigned_to: str = None

class Deal(BaseModel):
    id: str = None
    title: str
    amt: float
    status: str = "open"
    customer_id: str = None
    assigned_to: str = None

class Note(BaseModel):
    id: str = None
    customer_id: str
    content: str
    type: str = "general"
    created_at: str = None

class Status(BaseModel):
    status: str

class User(BaseModel):
    id: str = None
    name: str
    email: str
    role: str = "sales_rep"

class Assignment(BaseModel):
    assigned_to: str

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "sales_rep"

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class AuditLog(BaseModel):
    id: str = None
    user_id: str = None
    action: str
    type: str = None
    resource_id: str = None
    details: str = None
    ip: str = None
    agent: str = None
    timestamp: str = None

@app.get("/customers")
def list_customers(request: Request, assigned_to: str = None, current_user: dict = Depends(get_current_user)):
    ip, agent = get_client_info(request)
    
    query = db.table('customers').select('*')
    if assigned_to:
        query = query.eq("assigned_to", assigned_to)
    elif current_user["role"] == "sales_rep":
        query = query.eq("assigned_to", current_user["id"])
    
    result = query.execute().data
    
    log_audit_event(
        user_id=current_user["id"],
        action="READ",
        type="customer",
        details=json.dumps({"filter": {"assigned_to": assigned_to}, "count": len(result)}),
        ip=ip,
        agent=agent
    )
    
    return result

@app.post("/customers")
def create_customer(customer: Customer, request: Request, current_user: dict = Depends(get_current_user)):
    ip, agent = get_client_info(request)
    data = customer.dict(exclude_unset=True)
    original_data = data.copy()
    data.pop("id", None)
    if data.get('assigned_to'):
        user = db.table("users").select("*").eq("id", data['assigned_to']).execute()
        if not user.data:
            raise HTTPException(status_code=400, detail="Assigned user not found")
    
    result = (db.table('customers').insert(data).execute()).data
    
    if result:
        log_audit_event(
            user_id=current_user["id"],
            action="CREATE",
            type="customer",
            resource_id=result[0].get("id"),
            details=json.dumps({"created_data": original_data}),
            ip=ip,
            agent=agent
        )
    
    return result

@app.put("/customers/{id}")
def update_customer(id: str, customer: Customer, request: Request, current_user: dict = Depends(get_current_user)):
    ip, agent = get_client_info(request)
    
    existing_customer = db.table("customers").select("*").eq("id", id).execute()
    if not existing_customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    if (current_user["role"] == "sales_rep" and 
        existing_customer.data[0].get("assigned_to") != current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to update this customer")
    data = customer.dict(exclude_unset=True)
    update_data = data.copy()
    data.pop("id", None)
    if data.get('assigned_to'):
        user = db.table("users").select("*").eq("id", data['assigned_to']).execute()
        if not user.data:
            raise HTTPException(status_code=400, detail="Assigned user not found")
    resp = db.table("customers").update(data).eq("id", id).execute()
    
    log_audit_event(
        user_id=current_user["id"],
        action="UPDATE",
        type="customer",
        resource_id=id,
        details=json.dumps({
            "old_data": existing_customer.data[0],
            "new_data": update_data
        }),
        ip=ip,
        agent=agent
    )
    
    return resp.data

@app.delete("/customers/{id}")
def delete_customer(id: str, request: Request, current_user: dict = Depends(get_current_user)):
    client_info = get_client_info(request)
    
    existing_customer = db.table("customers").select("*").eq("id", id).execute()
    if not existing_customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    if (current_user["role"] == "sales_rep" and 
        existing_customer.data[0].get("assigned_to") != current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this customer")
    resp = db.table("customers").delete().eq("id", id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    log_audit_event(
        user_id=current_user["id"],
        action="DELETE",
        type="customer",
        resource_id=id,
        details={"deleted_data": existing_customer.data[0]},
        **client_info
    )
    
    return {"ok": True}

@app.get("/customers/{id}")
def get_customer(id: str, current_user: dict = Depends(get_current_user)):
    customer = db.table("customers").select("*, users!customers_assigned_to_fkey(id, name, email)").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    if (current_user["role"] == "sales_rep" and 
        customer.data[0].get("assigned_to") != current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to view this customer")
    return customer.data[0]

@app.get("/deals")
def list_deals(assigned_to: str = None, current_user: dict = Depends(get_current_user)):
    query = db.table('deals').select('*, users!deals_assigned_to_fkey(id, name, email), customers!deals_customer_id_fkey(id, name, company)')
    if assigned_to:
        query = query.eq('assigned_to', assigned_to)
    elif current_user["role"] == "sales_rep":
        query = query.eq('assigned_to', current_user["id"])
    return query.execute().data



@app.post("/deals")
def create_deal(deal: Deal, current_user: dict = Depends(get_current_user)):
    data = deal.dict(exclude_unset=True)
    data.pop("id", None)
    if not data.get('assigned_to') and current_user["role"] == "sales_rep":
        data['assigned_to'] = current_user["id"]
    if data.get('assigned_to'):
        user = db.table("users").select("*").eq("id", data['assigned_to']).execute()
        if not user.data:
            raise HTTPException(status_code=400, detail="Assigned user not found")
    if data.get('customer_id'):
        customer = db.table("customers").select("*").eq("id", data['customer_id']).execute()
        if not customer.data:
            raise HTTPException(status_code=400, detail="Customer not found")
    return (db.table('deals').insert(data).execute()).data

@app.put("/deals/{deal_id}")
def update_deal(deal_id: str, deal: Deal, current_user: dict = Depends(get_current_user)):
    existing_deal = db.table("deals").select("*").eq("id", deal_id).execute()
    if not existing_deal.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    if (current_user["role"] == "sales_rep" and 
        existing_deal.data[0].get("assigned_to") != current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to update this deal")
    data = deal.dict(exclude_unset=True)
    data.pop("id", None)
    if data.get('assigned_to'):
        user = db.table("users").select("*").eq("id", data['assigned_to']).execute()
        if not user.data:
            raise HTTPException(status_code=400, detail="Assigned user not found")
    resp = db.table("deals").update(data).eq("id", deal_id).execute()
    return resp.data

@app.delete("/deals/{deal_id}")
def delete_deal(deal_id: str, current_user: dict = Depends(get_current_user)):
    existing_deal = db.table("deals").select("*").eq("id", deal_id).execute()
    if not existing_deal.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    if (current_user["role"] == "sales_rep" and 
        existing_deal.data[0].get("assigned_to") != current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this deal")
    resp = db.table("deals").delete().eq("id", deal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"ok": True}

@app.get("/deals/{deal_id}")
def get_deal(deal_id: str, current_user: dict = Depends(get_current_user)):
    deal = db.table("deals").select("*, users!deals_assigned_to_fkey(id, name, email), customers!deals_customer_id_fkey(id, name, company)").eq("id", deal_id).execute()
    if not deal.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    if (current_user["role"] == "sales_rep" and 
        deal.data[0].get("assigned_to") != current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to view this deal")
    return deal.data[0]

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
    if not data.get('assigned_to') and customer.data[0].get('assigned_to'):
        data['assigned_to'] = customer.data[0]['assigned_to']
    return (db.table("deals").insert(data).execute()).data

@app.get("/customers/{id}/deals")
def list_customer_deals(id: str):
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return (db.table("deals").select("*, users!deals_assigned_to_fkey(id, name, email)").eq("customer_id", id).execute()).data

@app.put("/deals/{deal_id}/status")
def update_deal_status(deal_id: str, status: Status):
    data = status.dict(exclude_unset=True)
    resp = db.table("deals").update(data).eq("id", deal_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return resp.data

@app.get("/deals/pipeline")
def get_deals_pipeline(assigned_to: str = None):
    query = db.table('deals').select('*, users!deals_assigned_to_fkey(id, name), customers!deals_customer_id_fkey(id, name, company)')
    if assigned_to:
        query = query.eq('assigned_to', assigned_to)
    deals = query.execute().data
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
def get_deals_summary(assigned_to: str = None):
    query = db.table('deals').select('*')
    if assigned_to:
        query = query.eq('assigned_to', assigned_to)
    
    deals = query.execute().data
    total = len(deals)
    win = [d for d in deals if d.get('status') == 'won' or d.get('stage') == 'won']
    lose = [d for d in deals if d.get('status') == 'lost' or d.get('stage') == 'lost']
    open = [d for d in deals if d.get('stage') in ['open', 'in_progress']]
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
        "average_deal_size": round(total_revenue / len(win), 2) if win else 0,
        "filtered_by_user": assigned_to is not None
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
def get_top_customers(assigned_to: str = None):
    customerq = db.table('customers').select('*')
    deal_query = db.table('deals').select('*')
    if assigned_to:
        customerq = customerq.eq('assigned_to', assigned_to)
        deal_query = deal_query.eq('assigned_to', assigned_to)
    customers = customerq.execute().data
    deals = deal_query.execute().data
    leaderboard = []
    for customer in customers:
        customer_deals = [d for d in deals if d.get('customer_id') == customer['id']]
        won_deals = [d for d in customer_deals if d.get('status') == 'won' or d.get('stage') == 'won']
        total = sum(d.get('amt', 0) for d in won_deals)
        if total > 0:
            leaderboard.append({
                "customer_id": customer['id'],
                "customer_name": customer.get('name'),
                "company": customer.get('company'),
                "email": customer.get('email'),
                "total_revenue": total,
                "deals_count": len(won_deals),
                "average_deal_size": round(total / len(won_deals), 2) if won_deals else 0,
                "assigned_to": customer.get('assigned_to')
            })
    leaderboard.sort(key=lambda x: x['total_revenue'], reverse=True)
    return {
        "top_customers": leaderboard[:10],
        "total_customers_with_revenue": len(leaderboard),
        "filtered_by_user": assigned_to is not None
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
def get_fun_fact():
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
            customers = [c for c in customers if c.get('name')]
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

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/")
def root():
    return {"message": "Welcome to the CRM API"}

@app.get("/users")
def get_users():
    users = (db.table("users").select("*").execute()).data
    return {"users": users}

@app.post("/users")
def create_user(user: User):
    db.table("users").insert(user.dict()).execute()
    return {"message": "User created successfully"}

@app.put("/users/{user_id}")
def update_user(user_id: str, user: User):
    db.table("users").update(user.dict()).where("id", user_id).execute()
    return {"message": "User updated successfully"}

@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    db.table("users").delete().where("id", user_id).execute()
    return {"message": "User deleted successfully"}

@app.get("/users/{user_id}")
def get_user(user_id: str):
    user = (db.table("users").select("*").where("id", user_id).execute()).data
    if not user:
        return {"error": "User not found"}
    return {"user": user}

@app.put("/customers/{id}/assign")
def assign_customer(id: str, assignment: Assignment):
    user = db.table("users").select("*").eq("id", assignment.assigned_to).execute()
    if not user.data:
        raise HTTPException(status_code=400, detail="User not found")
    
    customer = db.table("customers").select("*").eq("id", id).execute()
    if not customer.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    resp = db.table("customers").update({"assigned_to": assignment.assigned_to}).eq("id", id).execute()
    return {
        "success": True,
        "message": f"Customer assigned to {user.data[0]['name']}",
        "customer_id": id,
        "assigned_to": assignment.assigned_to
    }

@app.put("/deals/{deal_id}/assign")
def assign_deal(deal_id: str, assignment: Assignment):
    user = db.table("users").select("*").eq("id", assignment.assigned_to).execute()
    if not user.data:
        raise HTTPException(status_code=400, detail="User not found")
    deal = db.table("deals").select("*").eq("id", deal_id).execute()
    if not deal.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    resp = db.table("deals").update({"assigned_to": assignment.assigned_to}).eq("id", deal_id).execute()
    return {
        "success": True,
        "message": f"Deal assigned to {user.data[0]['name']}",
        "deal_id": deal_id,
        "assigned_to": assignment.assigned_to
    }

@app.get("/users/{user_id}/dashboard")
def get_user_dashboard(user_id: str):
    user = db.table("users").select("*").eq("id", user_id).execute()
    if not user.data:
        raise HTTPException(status_code=404, detail="User not found")
    acustomers = db.table("customers").select("*").eq("assigned_to", user_id).execute().data
    adeals = db.table("deals").select("*").eq("assigned_to", user_id).execute().data
    active_deals = [d for d in adeals if d.get('status') in ['open', 'in_progress']]
    wdeals = [d for d in adeals if d.get('status') == 'win']
    total_revenue = sum(d.get('amt', 0) for d in wdeals)
    potential_revenue = sum(d.get('amt', 0) for d in active_deals)
    return {
        "user": user.data[0],
        "assigned_customers": len(acustomers),
        "assigned_deals": len(adeals),
        "active_deals": len(active_deals),
        "won_deals": len(wdeals),
        "total_revenue": total_revenue,
        "potential_revenue": potential_revenue,
        "customers": acustomers[:5],
        "deals": adeals[:5]
    }

@app.get("/users/{user_id}/customers")
def get_user_customers(user_id: str):
    customers = db.table("customers").select("*").eq("assigned_to", user_id).execute().data
    return {"customers": customers}

@app.get("/users/{user_id}/deals")
def get_user_deals(user_id: str):
    deals = db.table("deals").select("*").eq("assigned_to", user_id).execute().data
    return {"deals": deals}

@app.get("/analytics/team-performance")
def get_team_performance():
    users = db.table("users").select("*").execute().data
    deals = db.table("deals").select("*").execute().data
    team_stats = []
    for user in users:
        udeals = [d for d in deals if d.get('assigned_to') == user['id']]
        wdeals = [d for d in udeals if d.get('stage') == 'won']
        adeals = [d for d in udeals if d.get('stage') in ['open', 'in_progress']]
        revenue = sum(d.get('amt', 0) for d in wdeals)
        potential = sum(d.get('amt', 0) for d in adeals)
        team_stats.append({
            "user_id": user['id'],
            "user_name": user.get('name'),
            "email": user.get('email'),
            "role": user.get('role'),
            "total_deals": len(udeals),
            "won_deals": len(wdeals),
            "active_deals": len(adeals),
            "revenue": revenue,
            "potential_revenue": potential,
            "win_rate": round((len(wdeals) / len(udeals) * 100), 2) if udeals else 0
        })
    team_stats.sort(key=lambda x: x['revenue'], reverse=True)
    return {
        "team_performance": team_stats,
        "total_team_revenue": sum(s['revenue'] for s in team_stats),
        "total_team_potential": sum(s['potential_revenue'] for s in team_stats)
    }

@app.post("/auth/register", response_model=Token)
def register(user_data: UserCreate, request: Request):
    client_info = get_client_info(request)
    
    exist = db.table("users").select("*").eq("email", user_data.email).execute()
    if exist.data:
        log_audit_event(
            action="REGISTER_FAILED",
            type="user",
            details={"reason": "Email already registered", "email": user_data.email},
            **client_info
        )
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    hashed, salt = custom_hash_password(user_data.password)
    user_dict = {
        "name": user_data.name,
        "email": user_data.email,
        "password_hash": hashed,
        "password_salt": salt,
        "role": user_data.role,
        "created_at": datetime.utcnow().isoformat()
    }
    result = db.table("users").insert(user_dict).execute()
    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to create user"
        )
    user_id = result.data[0]["id"]
    token_expiry = timedelta(seconds=JWT_EXPIRE)
    token = create_jwt_token(
        data={"sub": user_id}, expires_delta=token_expiry
    )
    
    log_audit_event(
        user_id=user_id,
        action="REGISTER",
        type="user",
        resource_id=user_id,
        details={"email": user_data.email, "role": user_data.role},
        **client_info
    )

    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/login", response_model=Token)
def login(user_credentials: UserLogin, request: Request):
    ip, agent = get_client_info(request)
    
    user = db.table("users").select("*").eq("email", user_credentials.email).execute()
    if not user.data:
        log_audit_event(
            action="LOGIN_FAILED",
            type="user",
            details=json.dumps({"reason": "User not found", "email": user_credentials.email}),
            ip=ip,
            agent=agent
        )
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_data = user.data[0]
    if not verify(user_credentials.password, user_data["password_hash"], user_data["password_salt"]):
        log_audit_event(
            user_id=user_data["id"],
            action="LOGIN_FAILED",
            type="user",
            details=json.dumps({"reason": "Invalid password", "email": user_credentials.email}),
            ip=ip,
            agent=agent
        )
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_expiry = timedelta(seconds=JWT_EXPIRE)
    token = create_jwt_token(
        data={"sub": user_data["id"]}, expires_delta=token_expiry
    )
    
    log_audit_event(
        user_id=user_data["id"],
        action="LOGIN",
        type="user",
        details=json.dumps({"email": user_credentials.email}),
        ip=ip,
        agent=agent
    )
    
    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/refresh", response_model=Token)
def refresh_token(current_user: dict = Depends(get_current_user)):
    token_expiry = timedelta(seconds=JWT_EXPIRE)
    token = create_jwt_token(
        data={"sub": current_user["id"]}, expires_delta=token_expiry
    )

    return {"access_token": token, "token_type": "bearer"}

@app.get("/auth/me")
def get_current_user_info(current_user: dict = Depends(get_current_user)):
    user_info = {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user["role"]
    }
    return user_info

@app.post("/auth/change-password")
def change_password(password_data: PasswordChange, current_user: dict = Depends(get_current_user)):
    if not verify(password_data.current_password, current_user["password_hash"], current_user["password_salt"]):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect"
        )
    new_hashed_password, new_salt = custom_hash_password(password_data.new_password)
    result = db.table("users").update({
        "password_hash": new_hashed_password,
        "password_salt": new_salt
    }).eq("id", current_user["id"]).execute()
    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to update password"
        )

    return {"message": "Password changed successfully"}

@app.get("/audit-logs")
def get_audit_logs(
    request: Request,
    current_user: dict = Depends(get_current_user),
    user_id: str = None,
    action: str = None,
    type: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    offset: int = 0
):
    if current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized to view audit logs")
    
    client_info = get_client_info(request)
    
    query = db.table("audit_logs").select("*, users!audit_logs_user_id_fkey(name, email)")
    
    if user_id:
        query = query.eq("user_id", user_id)
    if action:
        query = query.eq("action", action)
    if type:
        query = query.eq("type", type)
    if start_date:
        query = query.gte("timestamp", start_date)
    if end_date:
        query = query.lte("timestamp", end_date)
    
    result = query.order("timestamp", desc=True).range(offset, offset + limit - 1).execute()
    
    log_audit_event(
        user_id=current_user["id"],
        action="VIEW_AUDIT_LOGS",
        type="audit_log",
        details={
            "filters": {
                "user_id": user_id,
                "action": action,
                "type": type,
                "start_date": start_date,
                "end_date": end_date
            },
            "pagination": {"limit": limit, "offset": offset},
            "count": len(result.data)
        },
        **client_info
    )
    
    return {
        "audit_logs": result.data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(result.data)
        }
    }

@app.get("/audit-logs/user/{user_id}")
def get_user_audit_logs(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    limit: int = 50
):
    if current_user["id"] != user_id and current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized to view these audit logs")
    
    client_info = get_client_info(request)
    
    result = db.table("audit_logs").select("*").eq("user_id", user_id).order("timestamp", desc=True).limit(limit).execute()
    
    log_audit_event(
        user_id=current_user["id"],
        action="VIEW_USER_AUDIT_LOGS",
        type="audit_log",
        details={"target_user_id": user_id, "count": len(result.data)},
        **client_info
    )
    
    return {
        "user_id": user_id,
        "audit_logs": result.data,
        "count": len(result.data)
    }

@app.get("/audit-logs/resource/{type}/{resource_id}")
def get_resource_audit_logs(
    type: str,
    resource_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized to view resource audit logs")
    
    client_info = get_client_info(request)
    
    result = db.table("audit_logs").select("*, users!audit_logs_user_id_fkey(name, email)").eq("type", type).eq("resource_id", resource_id).order("timestamp", desc=True).execute()
    
    log_audit_event(
        user_id=current_user["id"],
        action="VIEW_RESOURCE_AUDIT_LOGS",
        type="audit_log",
        details={
            "target_type": type,
            "target_resource_id": resource_id,
            "count": len(result.data)
        },
        **client_info
    )
    
    return {
        "type": type,
        "resource_id": resource_id,
        "audit_logs": result.data,
        "count": len(result.data)
    }

@app.post("/generate-email")
def gen_email(request: dict, current_user: dict = Depends(get_current_user)):
    customer_id = request.get("customer_id")
    type = request.get("type")
    customer = db.table("customers").select("*").eq("id", customer_id).execute()
    deals = db.table("deals").select("*").eq("customer_id", customer_id).execute()
    r = requests.post("https://ai.hackclub.com/chat/completions", headers={
        "Content-Type": "application/json"
    }, json={
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "user", "content": f"""
                Write a professional {type} email for:
                Customer: {customer['name']} at {customer.get('company')}
                Email: {customer.get('email')}
                Active Deals: {len(deals)} worth ${sum(d.get('amt', 0) for d in deals)}

                Make it:
                - Professional but friendly
                - Personalized
                - Under 150 words

                Include subject line."""}
        ]
    })
    return {"email": r.json()['choices'][0]['message']['content']}

@app.post("handle-objection")
def handle_objection(request: dict, current_user: dict = Depends(get_current_user)):
    """Get AI help for handling customer objections"""
    objection = request.get("objection")
    context = request.get("context", "")
    
    r = requests.post("https://ai.hackclub.com/chat/completions", headers={
        "Content-Type": "application/json"
    }, json={
        "model": "openai/gpt-oss-120b",
        "messages": [{
            "role": "user",
            "content": f"""
            help handle this sales objection:
            objection: "{objection}"
            context: {context}

            provide:
            1. 3 different response approaches
            2. questions to ask back
            3. evidence/proof points to use
            4. how to redirect conversation
            5. when to concede vs push back
            be practical and conversational."""
                    }]
    })
    
    return {"response": r.json()['choices'][0]['message']['content']}

@app.post("/meeting-prep")
def meeting_prep(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = db.table("customers").select("*").eq("id", customer_id).execute().data[0]
    deals = db.table("deals").select("*").eq("customer_id", customer_id).execute().data
    notes = db.table("notes").select("*").eq("customer_id", customer_id).execute().data[-5:]
    r = requests.post("https://ai.hackclub.com/chat/completions", headers={
        "Content-Type": "application/json"
    }, json={
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "user", "content": f"""
                Create a meeting prep brief for:
                Customer: {customer['name']} ({customer.get('company')})
                Active Deals: {len(deals)} worth ${sum(d.get('amt', 0) for d in deals)}
                Recent History: {len(notes)} recent interactions

                Provide:
                1. Key talking points
                2. Questions to ask
                3. Potential objections & responses
                4. Goals for this meeting
                5. Follow-up actions

                Keep it concise and actionable."""}
        ]
    })
    return {"prep": r.json()['choices'][0]['message']['content']}
