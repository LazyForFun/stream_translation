# Stream Translate

即時直播字幕翻譯工具。擷取電腦系統音訊,用 Whisper 語音辨識,再透過 OpenAI 或 Gemini 翻成繁體中文,顯示在置頂的透明浮動視窗上。

## 功能

- 擷取系統音訊(Windows),即時語音辨識(faster-whisper,`large-v3-turbo`)
- 依停頓與句子分段,翻譯時帶入前兩句作為上下文
- 翻譯服務可切換:OpenAI(`gpt-5.4-mini`)或 Gemini(`gemini-3.5-flash-lite`)
- 透明、無邊框、永遠置頂的視窗
- API key 使用 Windows DPAPI 加密儲存在本機,不會寫進專案

## 架構

| 資料夾 | 說明 |
| --- | --- |
| `backend/` | FastAPI 後端:語音辨識、翻譯、API key 儲存(WebSocket + HTTP,埠 8000) |
| `backend/system_audio_ws_client.py` | 擷取系統音訊並透過 WebSocket 傳給後端 |
| `frontend/` | Electron + React + Vite 前端,啟動時會自動開啟後端與音訊程序 |

## 開發環境

需求:Windows、Python 3.x、Node.js。

```bash
# 後端
cd backend
pip install -r requirements.txt
python app.py            # http://127.0.0.1:8000

# 前端
cd frontend
npm install
npm start                # 同時啟動 vite 與 electron
```

注意:開發模式下 Electron 會執行 `backend/dist/app.exe`,所以需要先打包過後端(見下方),或自行調整 `frontend/electron/main.js`。

## 打包

```bash
# 1. 打包後端
cd backend
pyinstaller app.spec --noconfirm
pyinstaller system_audio_ws_client.spec --noconfirm

# 2. 打包前端(會把 backend/dist 一併放進去)
cd ../frontend
npm run build
npm run dist
```

輸出位置:`frontend/release/win-unpacked/StreamTranslate.exe`(免安裝資料夾)。

## 使用方式

1. 開啟 `StreamTranslate.exe`
2. 點設定,選擇翻譯服務(OpenAI / Gemini),輸入對應的 API key 後儲存
3. 播放要翻譯的影片或直播,字幕會顯示在視窗中

兩家服務的 key 各自獨立儲存,切換服務不需要重新輸入。也可以用環境變數 `OPENAI_API_KEY`、`GEMINI_API_KEY` 當作預設值(放在 `backend/.env`)。

## 設定檔位置

`%APPDATA%\StreamTranslate\`

- `api_key.bin`:OpenAI key(加密)
- `gemini_api_key.bin`:Gemini key(加密)
- `settings.json`:目前選擇的翻譯服務

## 已知限制

- 僅支援 Windows(系統音訊擷取與 key 加密都依賴 Windows)
- Gemini 單句翻譯延遲約 5~6 秒,比 OpenAI 慢
- 翻譯失敗(key 無效、額度用完)時,畫面上不會顯示錯誤訊息
