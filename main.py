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
    You are a medical expert assistant. Analyze this medical report and provide:
    
    1. Simple Summary: Explain what this report is about in simple language anyone can understand
    2. Key Findings: List the important values and what they mean
    3. Risk Flags: Highlight anything that is abnormal or needs attention
    4. Recommendations: What should the patient discuss with their doctor
    
    Be clear, compassionate, and avoid complex medical jargon.
    
    Medical Report:
    {text[:3000]}
    """
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    )
    
    return {"analysis": chat_completion.choices[0].message.content}