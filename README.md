# FoodShield AI — Food Security Decision Support System

> **Predict. Prevent. Protect.**  
> An AI-powered agricultural decision-support engine that analyzes localized crop distress signals before they cascade into wider food-system crises and ecosystem instability.

---

## 🌟 What FoodShield AI Is

FoodShield AI goes beyond simple crop disease detection. It models systemic risk by predicting how agricultural disruptions cascade through interconnected supply chains:

```
Crop Damage / Disease 
   ➔ Reduced Crop Production 
   ➔ Livestock Feed Shortages 
   ➔ Reduced Livestock Yield 
   ➔ Food Price Inflation 
   ➔ Food Insecurity & Malnutrition 
   ➔ Increased Wildlife Pressure 
   ➔ Ecosystem Imbalance & Systemic Failure
```

---

## 🚀 Quick Start (How to Run)

FoodShield AI is built as a zero-dependency, lightweight web application.

### Step 1: Configure Environment (`.env`)
Create or edit the `.env` file in the root directory and insert your Google Gemini API key:

```env
GEMINI_MODEL=gemini-3.5-flash
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

*(You can also set/override the key at runtime via the **API Key** button in the top navigation bar of the web app).*

### Step 2: Run Locally
Serve the application using a local HTTP server:

```bash
# Using Python
python3 -m http.server 8000

# Using Node / npx
npx serve .
```

Open `http://localhost:8000` in your web browser.

---

## ✨ Key Features

1. **Structured & Custom Text Inputs**: Combine structured parameters (crop damage %, weather, water, livestock dependency) with free-form custom field notes.
2. **Light & Dark Mode**: Native support for Dark mode, Light mode, and automatic device theme matching (`prefers-color-scheme`).
3. **One-Click Demo Scenario**: Click **"Load Demo Scenario"** to test a high-risk rice crop scenario with pre-filled field notes.
4. **Live Generative AI Analysis**: Calls Google Gemini (`gemini-3.5-flash`) with structured JSON output and robust auto-repair fallback.
5. **Food Collapse Risk Index**: Visual risk gauge with color-coded severity levels (Low, Moderate, High, Critical).
6. **Actionable Intervention Plan**: 3-tiered mitigation advice grouped into *Immediate (0-48h)*, *Short-Term (7 Days)*, and *Long-Term Prevention*.
7. **Systemic Cascade Timeline**: Visual timeline illustrating the "Broken World" domino effect sequence.
8. **Information Pages**: Built-in SPA sections for *About Project & Methodology*, *Agri Guidance Playbook*, and *Research & Global Datasets*.

---

## 🔒 Security & Deployment Note

> **IMPORTANT SECURITY WARNING**:  
> Direct browser-side API calls (`js/gemini.js`) and `.env` parsing are used here strictly for fast hackathon/student demonstration purposes. Production applications **must** proxy Gemini API requests through a secure serverless function or backend (e.g., Express.js, Cloud Functions, FastAPI) to keep API keys secure.
