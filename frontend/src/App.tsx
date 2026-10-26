import { useEffect, useMemo, useState } from "react";

type SubtitleMessage = {
  type: "subtitle" | "buffering";
  chunk_index: number;
  original_text: string;
  translated_text: string;
  language: string;
  raw_language?: string;
  language_probability?: number;
  is_final: boolean;
};

type SubtitleItem = SubtitleMessage & {
  id: number;
  createdAt: number;
};

export default function App() {
  const [connected, setConnected] = useState(false);
  const [subtitles, setSubtitles] = useState<SubtitleItem[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [apiKeySaved, setApiKeySaved] = useState(false);
  const [savingKey, setSavingKey] = useState(false);

  const pushApiKeyToBackend = async (key: string) => {
    const res = await fetch("http://127.0.0.1:8000/set-api-key", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        api_key: key
      })
    });

    if (!res.ok) {
      throw new Error("Failed to save API key");
    }
  };

  const clearApiKeyFromBackend = async () => {
    const res = await fetch("http://127.0.0.1:8000/clear-api-key", {
      method: "POST"
    });

    if (!res.ok) {
      throw new Error("Failed to clear API key");
    }
  };

  useEffect(() => {
    refreshApiKeyStatus();
  }, []);

  const fetchApiKeyStatus = async () => {
    const res = await fetch("http://127.0.0.1:8000/api-key-status");

    if (!res.ok) {
      throw new Error("Failed to fetch API key status");
    }

    const data = await res.json();
    return Boolean(data.has_api_key);
  };

  const refreshApiKeyStatus = async () => {
    try {
      const hasKey = await fetchApiKeyStatus();
      setApiKeySaved(hasKey);
    } catch (error) {
      console.error(error);
      setApiKeySaved(false);
    }
  };

  useEffect(() => {
  let ws: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let isUnmounted = false;

  const connectWebSocket = () => {
      ws = new WebSocket("ws://127.0.0.1:8000/ws/subtitles");

      ws.onopen = () => {
        if (isUnmounted) return;
        setConnected(true);
        refreshApiKeyStatus();
        console.log("Subtitle websocket connected");
      };

      ws.onclose = () => {
        if (isUnmounted) return;
        setConnected(false);
        console.log("Subtitle websocket closed. Reconnecting in 3 seconds...");

        reconnectTimer = window.setTimeout(() => {
          connectWebSocket();
        }, 3000);
      };

      ws.onerror = () => {
        if (isUnmounted) return;
        setConnected(false);
        ws?.close();
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type !== "subtitle") return;
        if (!data.original_text?.trim()) return;

        const newItem = {
          ...data,
          id: Date.now() + Math.random(),
          createdAt: Date.now()
        };

        setSubtitles((prev) => {
          const next = [newItem, ...prev];
          return next.slice(0, 300);
        });
      };
    };

    connectWebSocket();

    return () => {
      isUnmounted = true;

      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }

      ws?.close();
    };
  }, []);

  const statusText = useMemo(() => {
    return connected ? "已連線" : "未連線";
  }, [connected]);

  const saveApiKey = async () => {
    const trimmedKey = apiKey.trim();
    if (!trimmedKey) return;

    setSavingKey(true);

    try {
      await pushApiKeyToBackend(trimmedKey);
      await refreshApiKeyStatus();
      setApiKey("");
    } catch (error) {
      console.error(error);
      setApiKeySaved(false);
      alert("API key 儲存失敗");
    } finally {
      setSavingKey(false);
    }
  };

  const clearApiKey = async () => {
    try {
      await clearApiKeyFromBackend();
      await refreshApiKeyStatus();
      setApiKey("");
    } catch (error) {
      console.error(error);
      alert("API key 清除失敗");
    }
  };

  return (
    <div className="app">
      <div className="topbar">
        <div className="title">即時字幕面板</div>
        <div className={`status ${connected ? "online" : "offline"}`}>
          WebSocket：{statusText}
        </div>
        <div className="window-controls">
          <button onClick={() => window.electronAPI?.minimize()}>–</button>
          <button onClick={() => window.electronAPI?.close()}>✕</button>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-title">OpenAI API Key</div>

        <div className="settings-row">
          <input
            className="api-input"
            type="password"
            value={apiKey}
            placeholder="輸入你的 OpenAI API key"
            onChange={(e) => setApiKey(e.target.value)}
          />
          <button className="save-btn" onClick={saveApiKey} disabled={savingKey}>
            {savingKey ? "儲存中..." : "儲存"}
          </button>
          <button className="danger-btn" onClick={clearApiKey}>
            清除
          </button>
        </div>

        <div className="settings-hint">
          狀態：{apiKeySaved ? "已設定" : "尚未設定"}
        </div>
      </div>

      <div className="subtitle-stage">
        {subtitles.length === 0 ? (
          <div className="empty">等待字幕中…</div>
        ) : (
          subtitles.map((item) => (
            <div className="subtitle-block" key={item.id}>
              <div className="translated-line">
                {item.translated_text || "（尚未翻譯）"}
              </div>

              <div className="original-line">{item.original_text}</div>

              <div className="meta-line">
                <span>#{item.chunk_index}</span>
                <span>{item.language}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}