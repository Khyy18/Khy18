import { useCallback, useEffect, useRef, useState } from 'react';
import { useWebSocket, WSMessage } from '../hooks/useWebSocket';

const STATUS_TEXTS = [
  '\u0410\u0441\u0442\u0440\u043e\u043b\u043e\u0433 \u0441\u043b\u0443\u0448\u0430\u0435\u0442...',
  '\u0421\u043e\u0432\u0435\u0442\u0443\u0435\u0442\u0441\u044f \u0441\u043e \u0437\u0432\u0435\u0437\u0434\u0430\u043c\u0438...',
  '\u0427\u0438\u0442\u0430\u0435\u0442 \u043a\u0430\u0440\u0442\u0443 \u043d\u0435\u0431\u0430...',
  '\u041d\u0430\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u0435\u0442 \u0441\u0432\u044f\u0437\u044c \u0441 \u043a\u043e\u0441\u043c\u043e\u0441\u043e\u043c...',
  '\u0420\u0430\u0441\u043a\u043b\u0430\u0434\u044b\u0432\u0430\u0435\u0442 \u0430\u0441\u043f\u0435\u043a\u0442\u044b...',
];

interface AstroCallProps {
  sessionId: string;
  wsBaseUrl?: string;
}

export function AstroCall({ sessionId, wsBaseUrl = 'ws://localhost:8000' }: AstroCallProps) {
  const [isMuted, setIsMuted] = useState(false);
  const [balance, setBalance] = useState<number | null>(null);
  const [terminated, setTerminated] = useState(false);
  const [statusIndex, setStatusIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const userVideoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const { connected, lastMessage } = useWebSocket({
    url: `${wsBaseUrl}/ws/billing/${sessionId}`,
    autoConnect: true,
  });

  // Handle WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;

    const msg: WSMessage = lastMessage;
    if (msg.event_type === 'BALANCE_UPDATE') {
      setBalance(msg.balance_after);
    } else if (msg.event_type === 'TERMINATE_CALL') {
      setTerminated(true);
    }
  }, [lastMessage]);

  // Rotate status text
  useEffect(() => {
    const interval = setInterval(() => {
      setStatusIndex((prev) => (prev + 1) % STATUS_TEXTS.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  // Initialize user camera
  useEffect(() => {
    let cancelled = false;

    const initCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: 160, height: 160 },
          audio: true,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (userVideoRef.current) {
          userVideoRef.current.srcObject = stream;
        }
      } catch {
        // Camera access denied or unavailable
      }
    };

    initCamera();

    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };
  }, []);

  const handleMuteToggle = useCallback(() => {
    setIsMuted((prev) => {
      const newMuted = !prev;
      if (streamRef.current) {
        streamRef.current.getAudioTracks().forEach((track) => {
          track.enabled = !newMuted;
        });
      }
      return newMuted;
    });
  }, []);

  const handleEndCall = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    window.history.back();
  }, []);

  const handleTopUp = useCallback(() => {
    // Redirect to balance top-up (Telegram payment or external link)
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.openLink('/balance/topup');
    }
  }, []);

  const formatBalance = (coins: number | null): string => {
    if (coins === null) return '--';
    const minutes = Math.floor(coins / 10);
    return `${minutes} \u043c\u0438\u043d`;
  };

  if (terminated) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-6">
        <div className="text-center">
          <div className="mb-4 text-6xl">{'\u2B50'}</div>
          <h2 className="mb-2 text-2xl font-bold text-white">
            {'\u0411\u0430\u043b\u0430\u043d\u0441 \u0438\u0441\u0447\u0435\u0440\u043f\u0430\u043d'}
          </h2>
          <p className="mb-6 text-tg-hint">
            {'\u041f\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u0431\u0430\u043b\u0430\u043d\u0441, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u043a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0430\u0446\u0438\u044e'}
          </p>
          <button
            onClick={handleTopUp}
            className="rounded-full bg-tg-button px-8 py-3 text-lg font-semibold text-tg-button-text transition-transform active:scale-95"
          >
            {'\u041f\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u044c'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex flex-col bg-black">
      {/* Full-screen AI avatar video */}
      <video
        ref={videoRef}
        className="absolute inset-0 h-full w-full object-cover"
        autoPlay
        playsInline
        muted
      />

      {/* Floating user camera preview */}
      <div className="absolute right-4 top-4 z-10 h-20 w-20 overflow-hidden rounded-full border-2 border-white/30 shadow-lg">
        <video
          ref={userVideoRef}
          className="h-full w-full object-cover"
          autoPlay
          playsInline
          muted
        />
      </div>

      {/* Connection status indicator */}
      <div className="absolute left-4 top-4 z-10 flex items-center gap-2">
        <div
          className={`h-2 w-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`}
        />
        <span className="text-xs text-white/70">
          {connected ? '\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e' : '\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435...'}
        </span>
      </div>

      {/* Emotion status indicator */}
      <div className="absolute inset-x-0 top-1/3 z-10 flex justify-center">
        <div className="rounded-full bg-black/40 px-5 py-2 backdrop-blur-sm">
          <p className="animate-pulse-text text-center text-sm font-medium text-white">
            {STATUS_TEXTS[statusIndex]}
          </p>
        </div>
      </div>

      {/* Bottom control bar */}
      <div className="absolute inset-x-0 bottom-0 z-10 flex items-center justify-center gap-6 bg-gradient-to-t from-black/80 to-transparent pb-10 pt-16">
        {/* Mute button */}
        <button
          onClick={handleMuteToggle}
          className={`flex h-14 w-14 items-center justify-center rounded-full transition-transform active:scale-90 ${
            isMuted ? 'bg-red-500/80' : 'bg-white/20 backdrop-blur-sm'
          }`}
          aria-label={isMuted ? '\u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d' : '\u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-6 w-6 text-white"
          >
            {isMuted ? (
              <path d="M1.5 4.5l21 15m-21-15v15l6-4.5h3l3 3v-13.5l-3 3h-3l-6-3z" />
            ) : (
              <path d="M12 1.5a3 3 0 013 3v7.5a3 3 0 01-6 0V4.5a3 3 0 013-3zm-7.5 10.5a.75.75 0 011.5 0 6 6 0 0012 0 .75.75 0 011.5 0 7.5 7.5 0 01-6.75 7.462V21h3a.75.75 0 010 1.5h-7.5a.75.75 0 010-1.5h3v-1.538A7.5 7.5 0 014.5 12z" />
            )}
          </svg>
        </button>

        {/* End call button */}
        <button
          onClick={handleEndCall}
          className="flex h-16 w-16 items-center justify-center rounded-full bg-red-600 shadow-lg transition-transform active:scale-90"
          aria-label={'\u0417\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u044c \u0437\u0432\u043e\u043d\u043e\u043a'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-7 w-7 text-white"
          >
            <path d="M1.5 4.5a3 3 0 013-3h1.372c.86 0 1.61.586 1.819 1.42l1.105 4.423a1.875 1.875 0 01-.694 1.955l-1.293.97c-.135.101-.164.249-.126.352a11.285 11.285 0 006.697 6.697c.103.038.25.009.352-.126l.97-1.293a1.875 1.875 0 011.955-.694l4.423 1.105c.834.209 1.42.959 1.42 1.82V19.5a3 3 0 01-3 3h-2.25C8.552 22.5 1.5 15.448 1.5 6.75V4.5z" />
          </svg>
        </button>

        {/* Balance counter badge */}
        <div className="flex h-14 items-center rounded-full bg-white/20 px-4 backdrop-blur-sm">
          <span className="text-sm font-semibold text-white">
            {formatBalance(balance)}
          </span>
        </div>
      </div>
    </div>
  );
}
