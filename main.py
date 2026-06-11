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
import pytesseract
from PIL import Image
import io
import os
import time
from dotenv import load_dotenv
from groq import Groq
from database import create_tables, get_db, User, ReportHistory

load_dotenv()
create_tables()

# ── GROQ KEY ROTATION ──
GROQ_KEYS = [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
]
GROQ_KEYS = [k for k in GROQ_KEYS if k]  # Remove None values
current_key_index = 0

def get_groq_client():
    global current_key_index
    return Groq(api_key=GROQ_KEYS[current_key_index])

def rotate_key():
    global current_key_index
    current_key_index = (current_key_index + 1) % len(GROQ_KEYS)
    print(f"Rotated to Groq key {current_key_index + 1}")

def groq_call_with_retry(messages, model="llama-3.3-70b-versatile", max_retries=3):
    for attempt in range(max_retries):
        try:
            client = get_groq_client()
            response = client.chat.completions.create(
                messages=messages,
                model=model,
            )
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower() or "quota" in error_str.lower():
                print(f"Rate limit hit on key {current_key_index + 1}, rotating...")
                rotate_key()
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("All Groq API keys exhausted. Please try again later.")

SECRET_KEY = "mediscan-secret-key-2025-rishav"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp']

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
    mode: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    text = ""

    file_ext = file.filename.split('.')[-1].lower() if file.filename else ""

    if file_ext in IMAGE_EXTENSIONS:
        try:
            image = Image.open(io.BytesIO(contents))
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            text = pytesseract.image_to_string(image)
        except Exception as e:
            return {"error": f"Could not process image: {str(e)}"}
    else:
        try:
            pdf = fitz.open(stream=contents, filetype="pdf")
            for page in pdf:
                text += page.get_text()
        except Exception as e:
            return {"error": f"Could not read PDF: {str(e)}"}

    if not text.strip():
        return {"error": "Could not extract text from file. For images, ensure the photo is clear and well-lit with visible text."}

    if mode == "doctor":
        english_prompt = f"""
You are a senior clinician reviewing a medical report. Provide a detailed clinical analysis including:

1. **Clinical Summary**: Brief overview using medical terminology.

2. **Parameter Analysis**: For each value provide:
   - Parameter name with reference ranges
   - Patient value vs normal range
   - Clinical significance
   - ICD-10 codes where applicable

3. **Differential Diagnosis**: List possible conditions based on findings, ranked by likelihood.

4. **Risk Stratification**: Classify overall risk as Low, Moderate, High, or Critical with justification.

5. **Clinical Recommendations**: Specific investigations, referrals, and treatment considerations.

6. **Follow-up Protocol**: Recommended monitoring intervals and parameters.

Use clinical terminology. Be precise and evidence-based.

Medical Report:
{text[:4000]}
"""
    else:
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

    try:
        analysis = groq_call_with_retry([{"role": "user", "content": english_prompt}])
    except Exception as e:
        return {"error": "High traffic — please wait a moment and try again."}

    # Diet & lifestyle recommendations
    lifestyle_prompt = f"""Based on this medical report analysis, provide exactly:
- 5 specific diet tips
- 3 specific exercise tips

Return ONLY a JSON object in this exact format, nothing else:
{{"diet": ["tip1", "tip2", "tip3", "tip4", "tip5"], "exercise": ["tip1", "tip2", "tip3"]}}

Medical report:
{text[:2000]}"""

    try:
        lifestyle_raw = groq_call_with_retry([{"role": "user", "content": lifestyle_prompt}])
        import json
        lifestyle_raw = lifestyle_raw.strip()
        if lifestyle_raw.startswith("```"):
            lifestyle_raw = lifestyle_raw.split("```")[1]
            if lifestyle_raw.startswith("json"):
                lifestyle_raw = lifestyle_raw[4:]
        lifestyle = json.loads(lifestyle_raw.strip())
    except:
        lifestyle = {"diet": [], "exercise": []}

    if language == "hi":
        hindi_prompt = f"""You are a professional Hindi translator. Translate the following medical analysis to Hindi (Devanagari script).

Rules:
- Translate ALL explanations and text to Hindi
- Keep numbers and medical values as-is (e.g. 154/98 mmHg, 7.9%, 148 mg/dL)
- Translate section headings to Hindi
- Do not add or remove any information
- Do not include any English sentences in output

Text to translate:
{analysis}"""

        try:
            analysis = groq_call_with_retry([{"role": "user", "content": hindi_prompt}])
        except Exception as e:
            pass  # Keep English if translation fails

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

    return {"analysis": analysis, "lifestyle": lifestyle, "mode": mode}

@app.post("/chat")
async def chat_with_report(
    question: str = Form(...),
    context: str = Form(...),
    language: Optional[str] = Form(None)
):
    prompt = f"""You are a compassionate medical assistant. The patient has received this medical report analysis:

{context}

The patient is now asking: {question}

Answer their question simply and clearly based on the report analysis above. Be reassuring but honest. Keep your answer under 150 words. Always remind them to consult their doctor for personalized advice."""

    try:
        answer = groq_call_with_retry([{"role": "user", "content": prompt}])
    except Exception as e:
        return {"answer": "High traffic — please wait a moment and try again."}

    if language == "hi":
        hindi_prompt = f"""Translate this medical response to Hindi (Devanagari script). Keep medical values and numbers as-is. Only translate the text:

{answer}"""
        try:
            answer = groq_call_with_retry([{"role": "user", "content": hindi_prompt}])
        except:
            pass

    return {"answer": answer}
@app.post("/email-report")
async def email_report(
    email: str = Form(...),
    analysis: str = Form(...),
    language: Optional[str] = Form(None)
):
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")

    subject = "Your MediScan AI Medical Report Analysis" if language != "hi" else "आपकी MediScan AI मेडिकल रिपोर्ट विश्लेषण"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background: #f8fafc; padding: 40px 20px; color: #1a1a2e;">
        <div style="max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(110deg, #3b82f6, #6366f1); padding: 28px 32px; border-radius: 12px; margin-bottom: 24px;">
                <h1 style="color: white; margin: 0; font-size: 24px;">MediScan AI</h1>
                <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 14px;">Medical Report Analysis</p>
            </div>
            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 28px;">
                <p style="color: #374151; font-size: 15px; line-height: 1.8;">{analysis.replace(chr(10), '<br>')}</p>
            </div>
            <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                MediScan AI — For informational purposes only. Always consult your doctor.
            </p>
        </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": "MediScan AI <onboarding@resend.dev>",
            "to": [email],
            "subject": subject,
            "html": html_content,
        }
        resend.Emails.send(params)
        return {"success": True, "message": "Report sent successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}
@app.get("/history")
async def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = db.query(ReportHistory).filter(
        ReportHistory.user_id == current_user.id
    ).order_by(ReportHistory.created_at.desc()).limit(10).all()
    return {"history": [{"file_name": r.file_name, "analysis": r.analysis, "date": str(r.created_at)} for r in records]}