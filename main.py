from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
import fitz  # pymupdf
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/analyze")
async def analyze_report(file: UploadFile = File(...)):
    contents = await file.read()
    
    # Extract text from PDF
    pdf = fitz.open(stream=contents, filetype="pdf")
    text = ""
    for page in pdf:
        text += page.get_text()
    
    if not text.strip():
        return {"error": "Could not extract text from PDF"}
    
    # Send to Groq AI
    prompt = f"""
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
    
    Medical Report:
    {text[:4000]}
    """
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    )
    
    return {"analysis": chat_completion.choices[0].message.content}