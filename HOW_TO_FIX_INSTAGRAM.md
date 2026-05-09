# 📸 Instagram Fix — Render Deployment

Instagram ಡೌನ್ಲೋಡ್ ಮಾಡಲು `INSTAGRAM_COOKIES` environment variable set ಮಾಡಬೇಕು.

---

## Step 1 — Chrome Extension Install ಮಾಡಿ
Chrome Web Store ನಲ್ಲಿ: **"Get cookies.txt LOCALLY"** install ಮಾಡಿ.

## Step 2 — Instagram Cookies Export ಮಾಡಿ
1. Chrome ನಲ್ಲಿ `instagram.com` ಗೆ ಹೋಗಿ, login ಮಾಡಿ
2. Extension icon ಕ್ಲಿಕ್ ಮಾಡಿ → **"Export"** ಕ್ಲಿಕ್ ಮಾಡಿ
3. `cookies.txt` ಎಂದು save ಮಾಡಿ

## Step 3 — Base64 ಆಗಿ Convert ಮಾಡಿ

**Linux / Mac (Terminal):**
```bash
base64 -w 0 cookies.txt
```

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.txt"))
```

Output ಅನ್ನು copy ಮಾಡಿ (ಉದ್ದವಾದ text ಬರುತ್ತದೆ).

## Step 4 — Render Dashboard ನಲ್ಲಿ Set ಮಾಡಿ
1. [render.com](https://render.com) → ನಿಮ್ಮ bot service ಗೆ ಹೋಗಿ
2. **Environment** tab ಕ್ಲಿಕ್ ಮಾಡಿ
3. **Add Environment Variable:**
   - Key: `INSTAGRAM_COOKIES`
   - Value: *(Step 3 ನ base64 text paste ಮಾಡಿ)*
4. **Save** → Service ಆಟೋಮ್ಯಾಟಿಕ್ ಆಗಿ redeploy ಆಗುತ್ತದೆ

## Step 5 — Test ಮಾಡಿ
Bot ಗೆ Instagram reel link ಕಳಿಸಿ — ಈಗ ಡೌನ್ಲೋಡ್ ಆಗಬೇಕು!

---

## ⚠️ Important
- `cookies.txt` ಅನ್ನು **GitHub ಗೆ push ಮಾಡಬೇಡಿ** — private ಆಗಿರಿಸಿ
- Cookies expire ಆದರೆ, ಮತ್ತೆ Step 2-4 repeat ಮಾಡಿ
- YouTube / TikTok / Twitter ಗೆ cookies ಬೇಕಿಲ್ಲ ✅
