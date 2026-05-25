from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import Optional
import fitz
import os
from dotenv import load_dotenv
from groq import Groq
from database import create_tables, get_db, User, ReportHistory

load_dotenv()
create_tables()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SECRET_KEY = "mediscan-secret-key-2025-rishav"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/register")
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = get_password_hash(user.password)
    new_user = User(name=user.name, email=user.email, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    token = create_access_token({"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer", "name": new_user.name}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "name": user.name}

@app.post("/analyze")
async def analyze_report(
    file: UploadFile = File(...),
    token: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    print(f"DEBUG: language = {language}")

    contents = await file.read()
    pdf = fitz.open(stream=contents, filetype="pdf")
    text = ""
    for page in pdf:
        text += page.get_text()

    if not text.strip():
        return {"error": "Could not extract text from PDF"}

    # Step 1: English analysis
    english_prompt = f"""
You are a senior medical expert with 20 years of experience explaining medical reports to patients.

Analyze this medical report thoroughly and provide:

1. **Simple Summary**: In 2-3 sentences, explain what this report is about in simple language a 10-year-old can understand.

2. **Key Findings**: List every important value found. For each value state:
   - The parameter name
   - The reported value
   - Whether it is Normal, Low, or High
   - What it means for the patient's health

3. **Risk Flags**: List any abnormal values or concerning patterns. For each risk:
   - Clearly state what is abnormal
   - Explain the potential health consequence
   - Rate severity as Mild, Moderate, or Severe

4. **Positive Findings**: Mention any values that are healthy and reassure the patient.

5. **Recommendations**: Give 3-5 specific, actionable steps the patient should take including lifestyle changes and what to discuss with their doctor.

6. **Urgency Level**: State whether this report needs Immediate Attention, Follow-up Within a Week, Routine Follow-up, or No Immediate Action needed.

Be compassionate, clear, and avoid complex medical jargon. Always remind the patient to consult their doctor.
Respond in English.

Medical Report:
{text[:4000]}
"""

    english_response = client.chat.completions.create(
        messages=[{"role": "user", "content": english_prompt}],
        model="llama-3.3-70b-versatile",
    )
    analysis = english_response.choices[0].message.content
    print(f"DEBUG: English analysis done, language={language}")

    # Step 2: Translate to Hindi if requested
    if language == "hi":
        print("DEBUG: Translating to Hindi...")
        hindi_prompt = f"""You are a professional Hindi translator. Translate the following medical analysis to Hindi (Devanagari script).

Rules:
- Translate ALL explanations and text to Hindi
- Keep numbers and medical values as-is (e.g. 154/98 mmHg, 7.9%, 148 mg/dL)
- Translate section headings to Hindi
- Do not add or remove any information
- Do not include any English sentences in output

Text to translate:
{analysis}"""

        hindi_response = client.chat.completions.create(
            messages=[{"role": "user", "content": hindi_prompt}],
            model="llama-3.3-70b-versatile",
        )
        analysis = hindi_response.choices[0].message.content
        print("DEBUG: Hindi translation done")

    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            user = db.query(User).filter(User.email == email).first()
            if user:
                history = ReportHistory(
                    user_id=user.id,
                    file_name=file.filename,
                    analysis=analysis
                )
                db.add(history)
                db.commit()
        except:
            pass

    return {"analysis": analysis}

@app.get("/history")
async def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = db.query(ReportHistory).filter(
        ReportHistory.user_id == current_user.id
    ).order_by(ReportHistory.created_at.desc()).limit(10).all()
    return {"history": [{"file_name": r.file_name, "analysis": r.analysis, "date": str(r.created_at)} for r in records]}