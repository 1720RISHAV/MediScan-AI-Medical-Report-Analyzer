# MediScan AI — Medical Report Analyzer

An AI-powered web application that analyzes medical reports and explains complex medical terminology in simple, easy-to-understand language.

## Live Demo
🔗 https://mediscan-ai-medical-report-analyzer.onrender.com

## Problem Statement
Most people receive medical reports but cannot understand what the values mean or whether they are at risk. MediScan AI bridges this gap by providing instant, clear explanations powered by advanced AI.

## Features
- Upload any medical report in PDF format
- Identifies key findings and abnormal values
- Flags health risks with clear explanations
- Provides actionable recommendations
- Clean, responsive professional UI

## Tech Stack
- **Backend:** Python, FastAPI
- **AI Model:** LLaMA 3.3 70B (via Groq API)
- **PDF Processing:** PyMuPDF
- **Frontend:** HTML5, CSS3, JavaScript
- **Deployment:** Render

## Installation & Setup

### Prerequisites
- Python 3.10+
- Groq API Key (free at console.groq.com)

### Steps
1. Clone the repository
git clone https://github.com/1720RISHAV/MediScan-AI-Medical-Report-Analyzer.git
cd MediScan-AI-Medical-Report-Analyzer
2. Install dependencies
pip install -r requirements.txt
3. Create a `.env` file
GROQ_API_KEY=your_groq_api_key_here
4. Run the application
python -m uvicorn main:app --reload
5. Open browser at `http://127.0.0.1:8000`

## Project Structure
MediScan-AI/
├── main.py          # FastAPI backend
├── index.html       # Frontend UI
├── requirements.txt # Dependencies
├── .env             # API keys (not tracked)
└── .gitignore       # Git ignore rules
## Author
**Rishav Kumar Singh**  
B.Tech CSE @ SRM Institute of Science and Technology  
[LinkedIn](https://linkedin.com/in/rishavkumarsingh590) | [GitHub](https://github.com/1720RISHAV)

## Disclaimer
MediScan AI is for informational purposes only. Always consult a qualified healthcare professional for medical advice.
