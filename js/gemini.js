/**
 * FoodShield AI - Gemini API Integration Module (.env Loader Enabled)
 */

// Configuration Defaults (overridden by .env if present)
let GEMINI_MODEL = "gemini-3.5-flash";
let GEMINI_API_KEY = "";

/**
 * Automatically fetch and parse .env file at startup
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

      // Strip quotes if present
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.substring(1, value.length - 1);
      }

      if (key === 'GEMINI_MODEL' && value) {
        GEMINI_MODEL = value;
      }
      if (key === 'GEMINI_API_KEY' && value && value !== 'YOUR_GEMINI_API_KEY') {
        GEMINI_API_KEY = value;
      }
    });

    console.log(`[FoodShield AI] Environment config loaded from .env (Model: ${GEMINI_MODEL})`);
  } catch (err) {
    // If running from file:// protocol or .env not readable, fallback to defaults/UI
    console.info("[FoodShield AI] Using runtime API key configuration.");
  }
}

// Auto-load .env on module load
loadEnvConfig();

/**
 * Update active API key at runtime
 * @param {string} newKey 
 */
function setApiKey(newKey) {
  if (newKey && newKey.trim()) {
    GEMINI_API_KEY = newKey.trim();
    return true;
  }
  return false;
}

/**
 * Get current API key
 * @returns {string}
 */
function getApiKey() {
  return GEMINI_API_KEY;
}

/**
 * Robust JSON extractor and cleaner
 * @param {string} rawText 
 * @returns {Object}
 */
function parseGeminiJson(rawText) {
  if (!rawText) {
    throw new Error("ไม่ได้รับข้อมูลจาก Gemini API");
  }

  let text = rawText.trim();

  // Strip markdown code fences if present
  text = text.replace(/^```json\s*/i, '');
  text = text.replace(/^```\s*/i, '');
  text = text.replace(/\s*```$/i, '');
  text = text.trim();

  // Extract JSON substring starting from first '{' to last '}'
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');

  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    text = text.substring(firstBrace, lastBrace + 1);
  }

  try {
    return JSON.parse(text);
  } catch (parseError) {
    console.warn("First JSON.parse attempt failed, attempting fallback cleanup...", parseError);

    // Clean common JSON syntax errors
    let cleaned = text
      .replace(/,\s*([\]}])/g, '$1') // Remove trailing commas
      .replace(/[\u0000-\u001F\u007F-\u009F]/g, ''); // Remove control chars

    try {
      return JSON.parse(cleaned);
    } catch (secondErr) {
      // Attempt auto-closing truncated JSON
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
 * Analyze agricultural food security risk using Google Gemini API
 * @param {Object} formData 
 * @returns {Promise<Object>} Formatted JSON analysis from Gemini in THAI
 */
async function analyzeFoodSecurityRisk(formData) {
  const currentKey = getApiKey();
  
  if (!currentKey || currentKey === "YOUR_GEMINI_API_KEY" || currentKey.trim() === "") {
    throw new Error("ไม่พบคีย์ Gemini API โปรดระบุ GEMINI_API_KEY ในไฟล์ .env หรือใส่คีย์ในช่องตั้งค่าคีย์ด้านบน");
  }

  // Construct clear prompt for Gemini
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

  const modelsToTry = Array.from(new Set([GEMINI_MODEL, "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash"])).filter(Boolean);
  let lastError = null;

  for (const model of modelsToTry) {
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${currentKey}`;

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          contents: [
            {
              parts: [
                {
                  text: promptText
                }
              ]
            }
          ],
          generationConfig: {
            responseMimeType: "application/json",
            temperature: 0.2,
            maxOutputTokens: 8192
          }
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const msg = errorData.error?.message || `HTTP ${response.status} ${response.statusText}`;
        lastError = new Error(`เกิดข้อผิดพลาดจาก Gemini API (${model}): ${msg}`);
        // If 404 (model not found), try next model fallback
        if (response.status === 404) {
          console.warn(`Model ${model} returned 404, trying next fallback model...`);
          continue;
        }
        throw lastError;
      }

      const data = await response.json();
      
      // Extract candidate text
      const candidateText = data.candidates?.[0]?.content?.parts?.[0]?.text;
      
      if (!candidateText) {
        throw new Error("ไม่ได้รับข้อมูลการตอบกลับจาก Gemini API");
      }

      // Robust JSON extraction and repair
      return parseGeminiJson(candidateText);

    } catch (err) {
      lastError = err;
      if (modelsToTry.indexOf(model) === modelsToTry.length - 1 || !err.message.includes("404")) {
        console.error("Gemini API Request Error:", err);
        throw err;
      }
    }
  }

  throw lastError || new Error("เกิดข้อผิดพลาดในการเชื่อมต่อ Gemini API");
}
