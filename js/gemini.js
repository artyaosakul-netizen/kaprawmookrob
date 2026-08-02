/**
 * FoodShield AI - Gemini API Integration Module
 * Uses /api/gemini serverless proxy on Vercel, or direct API call for local dev
 */

// Configuration Defaults (overridden by .env if present for local dev)
let GEMINI_MODEL = "gemini-3.5-flash";
let GEMINI_API_KEY = "";

/**
 * Load configuration from .env file (local development only)
 */
async function loadEnvConfig() {
  try {
    const response = await fetch('.env');
    if (!response.ok) return;

    const envText = await response.text();
    const lines = envText.split('\n');

    lines.forEach(line => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;

      const equalIdx = trimmed.indexOf('=');
      if (equalIdx === -1) return;

      const key = trimmed.substring(0, equalIdx).trim();
      let value = trimmed.substring(equalIdx + 1).trim();

      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.substring(1, value.length - 1);
      }

      if (key === 'GEMINI_MODEL' && value) GEMINI_MODEL = value;
      if (key === 'GEMINI_API_KEY' && value && value !== 'YOUR_GEMINI_API_KEY') GEMINI_API_KEY = value;
    });

    console.log(`[FoodShield AI] Config loaded from .env (Model: ${GEMINI_MODEL})`);
  } catch (err) {
    console.info("[FoodShield AI] No .env file found, will use server proxy.");
  }
}

// Auto-load config on module load
loadEnvConfig();

function setApiKey(newKey) {
  if (newKey && newKey.trim()) {
    GEMINI_API_KEY = newKey.trim();
    return true;
  }
  return false;
}

function getApiKey() {
  return GEMINI_API_KEY;
}

/**
 * Robust JSON extractor and cleaner
 */
function parseGeminiJson(rawText) {
  if (!rawText) {
    throw new Error("ไม่ได้รับข้อมูลจาก Gemini API");
  }

  let text = rawText.trim();
  text = text.replace(/^```json\s*/i, '');
  text = text.replace(/^```\s*/i, '');
  text = text.replace(/\s*```$/i, '');
  text = text.trim();

  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');

  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    text = text.substring(firstBrace, lastBrace + 1);
  }

  try {
    return JSON.parse(text);
  } catch (parseError) {
    let cleaned = text
      .replace(/,\s*([\]}])/g, '$1')
      .replace(/[\u0000-\u001F\u007F-\u009F]/g, '');

    try {
      return JSON.parse(cleaned);
    } catch (secondErr) {
      let repaired = cleaned;
      const openBrackets = (repaired.match(/\[/g) || []).length;
      const closeBrackets = (repaired.match(/\]/g) || []).length;
      const openBraces = (repaired.match(/\{/g) || []).length;
      const closeBraces = (repaired.match(/\}/g) || []).length;

      for (let i = 0; i < openBrackets - closeBrackets; i++) repaired += ']';
      for (let i = 0; i < openBraces - closeBraces; i++) repaired += '}';

      try {
        return JSON.parse(repaired);
      } catch (finalErr) {
        console.error("Raw Gemini output that failed parsing:", rawText);
        throw new Error(`รูปแบบข้อมูลจาก AI ไม่สมบูรณ์ (JSON Parse Error): ${parseError.message}`);
      }
    }
  }
}

/**
 * Build the Gemini request body from form data
 */
function buildGeminiRequestBody(formData) {
  const promptText = `
คุณคือผู้เชี่ยวชาญระดับสูงด้านระบบสนับสนุนการตัดสินใจเพื่อความมั่นคงทางอาหาร พลวัตการเกษตร และวิทยาศาสตร์ระบบนิเวศ (Agricultural Food-Security Decision-Support System)

จงวิเคราะห์ข้อมูลการเกษตรและสิ่งแวดล้อมต่อไปนี้:

ข้อมูลอินพุต:
- ชนิดพืชผล: ${formData.cropType}
- ประมาณการความเสียหายของพืชผล: ${formData.cropDamage}%
- สภาพอากาศ: ${formData.weather}
- ปริมาณน้ำที่มีอยู่: ${formData.water}
- อาการโรคและศัตรูพืช: ${formData.symptoms && formData.symptoms.length > 0 ? formData.symptoms.join(", ") : "ไม่พบอาการ"}
- ฟาร์มข้างเคียงได้รับผลกระทบจากโรคระบาด/ปัญหา: ${formData.nearbyOutbreak}
- ความพึ่งพาของปศุสัตว์ต่อพืชนี้เป็นอาหารสัตว์: ${formData.livestockDep}%
- แนวโน้มราคาอาหาร: ${formData.priceTrend}

ข้อความรายละเอียด/ข้อสังเกตเพิ่มเติมเฉพาะพื้นที่ (ถ้ามี):
"${formData.additionalNotes || "ไม่มีข้อความเพิ่มเติม"}"

ข้อกำหนดการวิเคราะห์:
1. ประเมินระดับความเสี่ยงของระบบอาหารล้มเหลว ("Low", "Moderate", "High", "Critical") และคะแนนความเสี่ยง (risk_score เป็นจำนวนเต็ม 0-100)
2. อธิบายสรุปสถานการณ์สั้นๆ 2-3 ประโยค ด้วยภาษามนุษย์ที่อ่านง่าย เป็นกันเอง เข้าใจง่าย ไม่งง ไม่ใช้วิชาการซับซ้อนเกินไป
3. ระบุปัจจัยความเสี่ยงหลัก / สาเหตุสำคัญ 2-4 ข้อ (สั้น กระชับ ชัดเจน)
4. แนะนำมาตรการแก้ไขที่ทำได้จริง แบ่งเป็น:
   - immediate_actions: สิ่งที่ต้องเร่งดำเนินการทันที (0-48 ชั่วโมง)
   - short_term_actions: มาตรการบรรเทาผลกระทบระยะสั้น (ภายใน 7 วัน)
   - long_term_actions: มาตรการป้องกันและสร้างความยืดหยุ่นระยะยาว
5. คาดการณ์ลำดับเหตุการณ์ผลกระทบลูกคลื่น (Domino Effect Timeline) จำนวน 5-7 ขั้นตอน (ภาษาไทย อ่านง่าย ชัดเจน)

สำคัญมาก:
- ข้อความทั้งหมดต้องเป็นภาษาไทยที่เป็นธรรมชาติ อ่านแล้วเข้าใจง่ายทันที
- ตอบเป็น raw JSON เท่านั้น ไม่ต้องมีคำเกริ่น ห้ามเว้นตัดจบกลางคีย์

รูปแบบ JSON ที่ต้องส่งคืน:
{
  "risk_level": "High",
  "risk_score": 85,
  "summary": "ข้อความสรุปภาษาไทยสั้นๆ 2-3 ประโยค",
  "causes": ["สาเหตุที่ 1", "สาเหตุที่ 2"],
  "immediate_actions": ["มาตรการเร่งด่วน 1", "มาตรการเร่งด่วน 2"],
  "short_term_actions": ["มาตรการระยะสั้น 1", "มาตรการระยะสั้น 2"],
  "long_term_actions": ["มาตรการระยะยาว 1", "มาตรการระยะยาว 2"],
  "domino_effect": [
    "1. พืชผลเสียหายรุนแรง",
    "2. ผลผลิตเกษตรลดลง",
    "3. อาหารสัตว์ขาดแคลน",
    "4. ผลผลิตปศุสัตว์ลดลง",
    "5. ราคาอาหารพุ่งสูงขึ้น",
    "6. ประชาชนขาดแคลนอาหาร",
    "7. เกิดผลกระทบต่อระบบนิเวศ"
  ]
}
`;

  return {
    contents: [{ parts: [{ text: promptText }] }],
    generationConfig: {
      responseMimeType: "application/json",
      temperature: 0.2,
      maxOutputTokens: 8192
    }
  };
}

/**
 * Analyze agricultural food security risk using Gemini API
 * Uses /api/gemini serverless proxy on Vercel, or direct API call for local dev
 */
async function analyzeFoodSecurityRisk(formData) {
  const requestBody = buildGeminiRequestBody(formData);
  const localKey = getApiKey();

  // Strategy 1: Try server proxy (/api/gemini) — works on Vercel deployment
  try {
    const proxyResponse = await fetch("/api/gemini", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody)
    });

    if (proxyResponse.ok) {
      const data = await proxyResponse.json();
      const candidateText = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (candidateText) {
        return parseGeminiJson(candidateText);
      }
    }

    // Check proxy error details
    const proxyError = await proxyResponse.json().catch(() => ({}));
    const proxyMsg = proxyError.error?.message || proxyError.error || "";

    // If proxy exists but key not set, throw clear error
    if (proxyResponse.status === 500 && proxyMsg.includes("not configured")) {
      throw new Error("เซิร์ฟเวอร์ยังไม่ได้ตั้งค่า GEMINI_API_KEY ใน Vercel Environment Variables");
    }

    // For non-404 errors, report them
    if (proxyResponse.status !== 404) {
      throw new Error(`เกิดข้อผิดพลาดจากเซิร์ฟเวอร์: ${proxyMsg || proxyResponse.statusText}`);
    }
  } catch (err) {
    // If it's a real error (not just "proxy doesn't exist"), re-throw unless we have a local key
    if (err.message && !err.message.includes("Failed to fetch") && !err.message.includes("NetworkError")) {
      if (!localKey) throw err;
    }
    console.info("[FoodShield AI] Server proxy unavailable, trying direct API call...");
  }

  // Strategy 2: Direct API call (local development with .env key)
  if (!localKey || localKey === "YOUR_GEMINI_API_KEY") {
    throw new Error("ไม่พบคีย์ Gemini API — โปรดตั้งค่า GEMINI_API_KEY ใน Vercel Environment Variables หรือในไฟล์ .env สำหรับการพัฒนา");
  }

  const modelsToTry = Array.from(new Set([GEMINI_MODEL, "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash"])).filter(Boolean);
  let lastError = null;

  for (const model of modelsToTry) {
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${localKey}`;

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const msg = errorData.error?.message || `HTTP ${response.status} ${response.statusText}`;
        lastError = new Error(`เกิดข้อผิดพลาดจาก Gemini API (${model}): ${msg}`);
        if (response.status === 404) {
          console.warn(`Model ${model} returned 404, trying next...`);
          continue;
        }
        throw lastError;
      }

      const data = await response.json();
      const candidateText = data.candidates?.[0]?.content?.parts?.[0]?.text;

      if (!candidateText) {
        throw new Error("ไม่ได้รับข้อมูลการตอบกลับจาก Gemini API");
      }

      return parseGeminiJson(candidateText);

    } catch (err) {
      lastError = err;
      if (modelsToTry.indexOf(model) === modelsToTry.length - 1 || !err.message.includes("404")) {
        throw err;
      }
    }
  }

  throw lastError || new Error("เกิดข้อผิดพลาดในการเชื่อมต่อ Gemini API");
}
