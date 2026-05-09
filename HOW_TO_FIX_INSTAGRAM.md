# 🔧 Instagram / Facebook ಡೌನ್ಲೋಡ್ ಆಗದಿದ್ದರೆ — Fix Guide

Instagram ಮತ್ತು Facebook ವಿಡಿಯೋ ಡೌನ್ಲೋಡ್ ಮಾಡಲು **cookies.txt** ಫೈಲ್ ಬೇಕು.

---

## Steps (ಕನ್ನಡದಲ್ಲಿ)

### Step 1 — Chrome Extension ಇನ್ಸ್ಟಾಲ್ ಮಾಡಿ
Chrome Web Store ನಲ್ಲಿ ಹುಡುಕಿ:
👉 **"Get cookies.txt LOCALLY"**
ಅದನ್ನು install ಮಾಡಿ.

### Step 2 — Instagram ಗೆ Login ಮಾಡಿ
Chrome ನಲ್ಲಿ [instagram.com](https://instagram.com) ಗೆ ಹೋಗಿ, ನಿಮ್ಮ account ನಲ್ಲಿ login ಮಾಡಿ.

### Step 3 — Cookies Export ಮಾಡಿ
1. Extension icon ಕ್ಲಿಕ್ ಮಾಡಿ
2. "Export" ಅಥವಾ download button ಕ್ಲಿಕ್ ಮಾಡಿ
3. `cookies.txt` ಎಂದು save ಮಾಡಿ

### Step 4 — Bot Folder ಗೆ Copy ಮಾಡಿ
`cookies.txt` ಫೈಲ್ ಅನ್ನು `main.py` ಇರುವ folder ಗೆ paste ಮಾಡಿ:
```
reels_bot_clean/
├── main.py
├── downloader.py
├── requirements.txt
└── cookies.txt   ← ಇಲ್ಲಿ ಇಡಿ
```

### Step 5 — Bot Restart ಮಾಡಿ
```bash
python main.py
```

---

## ⚠️ ಗಮನಿಸಿ
- `cookies.txt` ಅನ್ನು GitHub ಗೆ push ಮಾಡಬೇಡಿ (`.gitignore` ನಲ್ಲಿ add ಮಾಡಿ)
- Cookies expire ಆಗಬಹುದು — ಆದರೆ ಮತ್ತೆ export ಮಾಡಿ
- YouTube ಗೆ cookies ಇಲ್ಲದೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ

---

## Supported Platforms (cookies ಇಲ್ಲದೆ)
✅ YouTube, YouTube Shorts, YouTube Music
✅ TikTok (public videos)
✅ Twitter / X (public tweets)

## Supported Platforms (cookies ಬೇಕು)
🔒 Instagram Reels, Posts, IGTV
🔒 Facebook Videos
