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

type Provider = "openai" | "gemini";

const PROVIDER_LABELS: Record<Provider, string> = {
  openai: "OpenAI",
  gemini: "Gemini"
};

type AudioSource = {
  pid: number;
  name: string;
  active: boolean;
};

const SYSTEM_AUDIO = "system";

type SubtitleItem = SubtitleMessage & {
  id: number;
  createdAt: number;
};

export default function App() {
  const [connected, setConnected] = useState(false);
  const [subtitles, setSubtitles] = useState<SubtitleItem[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState<Provider>("openai");
  const [keysSaved, setKeysSaved] = useState<Record<Provider, boolean>>({
    openai: false,
    gemini: false
  });
  const [savingKey, setSavingKey] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [audioSources, setAudioSources] = useState<AudioSource[]>([]);
  const [audioSource, setAudioSource] = useState(SYSTEM_AUDIO);

  const pushApiKeyToBackend = async (key: string) => {
    const res = await fetch("http://127.0.0.1:8000/set-api-key", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        api_key: key,
        provider
      })
    });

    if (!res.ok) {
      throw new Error("Failed to save API key");
    }
  };

  const clearApiKeyFromBackend = async () => {
    const res = await fetch("http://127.0.0.1:8000/clear-api-key", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ provider })
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

    return await res.json();
  };

  const refreshApiKeyStatus = async () => {
    try {
      const data = await fetchApiKeyStatus();
      setProvider(data.provider);
      setKeysSaved({
        openai: Boolean(data.keys?.openai),
        gemini: Boolean(data.keys?.gemini)
      });
    } catch (error) {
      console.error(error);
      setKeysSaved({ openai: false, gemini: false });
    }
  };

  const refreshAudioSources = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/audio-sources");

      if (!res.ok) {
        throw new Error("Failed to fetch audio sources");
      }

      const data = await res.json();
      setAudioSources(data.sources ?? []);
    } catch (error) {
      console.error(error);
      setAudioSources([]);
    }
  };

  const changeAudioSource = async (next: string) => {
    const prev = audioSource;
    setAudioSource(next);

    try {
      await window.electronAPI?.setAudioSource(
        next === SYSTEM_AUDIO ? null : Number(next)
      );
    } catch (error) {
      console.error(error);
      setAudioSource(prev);
      alert("音訊來源切換失敗");
    }
  };

  useEffect(() => {
    if (showSettings) {
      refreshAudioSources();
    }
  }, [showSettings]);

  // 選定的程式關閉後,擷取程序會結束,退回系統音訊的顯示
  useEffect(() => {
    return window.electronAPI?.onAudioExited(() => {
      setAudioSource(SYSTEM_AUDIO);
      refreshAudioSources();
    });
  }, []);

  const changeProvider = async (next: Provider) => {
    const prev = provider;
    setProvider(next);
    setApiKey("");

    try {
      const res = await fetch("http://127.0.0.1:8000/set-provider", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ provider: next })
      });

      if (!res.ok) {
        throw new Error("Failed to set provider");
      }
    } catch (error) {
      console.error(error);
      setProvider(prev);
      alert("翻譯服務切換失敗");
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
          <button onClick={() => setShowSettings(true)} title="設定">⚙</button>
          <button onClick={() => window.electronAPI?.minimize()}>–</button>
          <button onClick={() => window.electronAPI?.close()}>✕</button>
        </div>
      </div>

      {showSettings && (
      <div className="modal-backdrop" onClick={() => setShowSettings(false)}>
      <div className="settings-card" onClick={(e) => e.stopPropagation()}>
        <div className="settings-title">音訊來源</div>

        <div className="settings-row">
          <select
            className="api-input"
            value={audioSource}
            onChange={(e) => changeAudioSource(e.target.value)}
          >
            <option value={SYSTEM_AUDIO}>整個系統</option>
            {audioSources.map((source) => (
              <option key={source.pid} value={String(source.pid)}>
                {source.name}
                {source.active ? "（播放中）" : ""}
              </option>
            ))}
          </select>
          <button className="save-btn" onClick={refreshAudioSources}>
            重新整理
          </button>
        </div>

        <div className="settings-title">翻譯服務</div>

        <div className="settings-row">
          <select
            className="api-input"
            value={provider}
            onChange={(e) => changeProvider(e.target.value as Provider)}
          >
            {(Object.keys(PROVIDER_LABELS) as Provider[]).map((p) => (
              <option key={p} value={p}>
                {PROVIDER_LABELS[p]}
              </option>
            ))}
          </select>
        </div>

        <div className="settings-title">{PROVIDER_LABELS[provider]} API Key</div>

        <div className="settings-row">
          <input
            className="api-input"
            type="password"
            value={apiKey}
            placeholder={`輸入你的 ${PROVIDER_LABELS[provider]} API key`}
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
          狀態：{keysSaved[provider] ? "已設定" : "尚未設定"}
        </div>

        <button className="close-btn" onClick={() => setShowSettings(false)}>
          關閉
        </button>
      </div>
      </div>
      )}

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