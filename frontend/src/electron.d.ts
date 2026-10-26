interface Window {
  electronAPI?: {
    minimize: () => void;
    close: () => void;
    setAudioSource: (pid: number | null) => Promise<void>;
    onAudioExited: (callback: () => void) => () => void;
  };
}
