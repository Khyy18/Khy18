import { useCallback, useEffect, useRef, useState } from 'react';
import { useWebSocket, WSMessage } from '../hooks/useWebSocket';
import { useCallWebSocket, PipelineState } from '../hooks/useCallWebSocket';
import { PaymentModal } from './PaymentModal';

const PIPELINE_STATUS_MAP: Record<PipelineState, string> = {
  LISTENING: '\u0421\u0442\u0435\u043B\u043B\u0430 \u0441\u043B\u0443\u0448\u0430\u0435\u0442...',
  THINKING: '\u0421\u043E\u0432\u0435\u0442\u0443\u0435\u0442\u0441\u044F \u0441\u043E \u0437\u0432\u0435\u0437\u0434\u0430\u043C\u0438...',
  SPEAKING: '\u0421\u0442\u0435\u043B\u043B\u0430 \u0433\u043E\u0432\u043E\u0440\u0438\u0442...',
  IDLE: '\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435...',
};

interface AstroCallProps {
  sessionId: string;
  token: string;
  wsBaseUrl?: string;
  apiBaseUrl?: string;
  onCallEnd?: () => void;
}

export function AstroCall({
  sessionId,
  token,
  wsBaseUrl = 'ws://localhost:8000',
  apiBaseUrl = 'http://localhost:8000',
  onCallEnd,
}: AstroCallProps) {
  const [isMuted, setIsMuted] = useState(false);
  const [balance, setBalance] = useState<number | null>(null);
  const [terminated, setTerminated] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const userVideoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);

  // Billing WebSocket with first-message auth
  const { connected: billingConnected, lastMessage } = useWebSocket({
    url: `${wsBaseUrl}/ws/billing/${sessionId}`,
    authToken: token,
    autoConnect: true,
  });

  // Call WebSocket with first-message auth and binary audio
  const { connected: callConnected, pipelineState, sendAudio, audioChunks } = useCallWebSocket({
    url: `${wsBaseUrl}/ws/call/${sessionId}`,
    authToken: token,
    autoConnect: true,
  });

  // Handle billing WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;

    const msg: WSMessage = lastMessage;
    if (msg.event_type === 'BALANCE_UPDATE') {
      setBalance(msg.balance_after);
    } else if (msg.event_type === 'TERMINATE_CALL') {
      setTerminated(true);
    }
  }, [lastMessage]);

  // Play received audio chunks
  useEffect(() => {
    if (audioChunks.length === 0) return;

    const latestChunk = audioChunks[audioChunks.length - 1];
    if (!latestChunk) return;

    const playAudio = async () => {
      try {
        if (!audioContextRef.current) {
          audioContextRef.current = new AudioContext();
        }
        const ctx = audioContextRef.current;
        const audioBuffer = await ctx.decodeAudioData(latestChunk.slice(0));
        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        source.start();
      } catch {
        // Failed to decode/play audio chunk
      }
    };

    playAudio();
  }, [audioChunks]);

  // Initialize user microphone
  useEffect(() => {
    let cancelled = false;

    const initMic = async () => {
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
        // Camera/mic access denied or unavailable
      }
    };

    initMic();

    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
    };
  }, []);

  // Send audio from microphone to server via WS
  useEffect(() => {
    if (!streamRef.current || !callConnected) return;

    const audioTrack = streamRef.current.getAudioTracks()[0];
    if (!audioTrack) return;

    // Use AudioContext + ScriptProcessor to capture raw audio and send
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(new MediaStream([audioTrack]));
    const processor = ctx.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      if (isMuted) return;
      const inputData = e.inputBuffer.getChannelData(0);
      const buffer = new ArrayBuffer(inputData.length * 2);
      const view = new DataView(buffer);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      }
      sendAudio(buffer);
    };

    source.connect(processor);
    processor.connect(ctx.destination);

    return () => {
      processor.disconnect();
      source.disconnect();
      ctx.close();
    };
  }, [callConnected, sendAudio, isMuted]);

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
    if (onCallEnd) {
      onCallEnd();
    } else {
      window.history.back();
    }
  }, [onCallEnd]);

  const handleTopUp = useCallback(() => {
    setShowPayment(true);
  }, []);

  const handlePaymentSuccess = useCallback(() => {
    setShowPayment(false);
    // Balance will be updated via billing WS
  }, []);

  const formatBalance = (coins: number | null): string => {
    if (coins === null) return '--';
    const minutes = Math.floor(coins / 10);
    return `${minutes} \u043C\u0438\u043D`;
  };

  const isConnected = billingConnected || callConnected;

  if (terminated) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-6">
        <div className="text-center">
          <div className="mb-4 text-6xl">&#x2B50;</div>
          <h2 className="mb-2 text-2xl font-bold text-white">
            &#x0411;&#x0430;&#x043B;&#x0430;&#x043D;&#x0441; &#x0438;&#x0441;&#x0447;&#x0435;&#x0440;&#x043F;&#x0430;&#x043D;
          </h2>
          <p className="mb-6 text-tg-hint">
            &#x041F;&#x043E;&#x043F;&#x043E;&#x043B;&#x043D;&#x0438;&#x0442;&#x0435; &#x0431;&#x0430;&#x043B;&#x0430;&#x043D;&#x0441;, &#x0447;&#x0442;&#x043E;&#x0431;&#x044B; &#x043F;&#x0440;&#x043E;&#x0434;&#x043E;&#x043B;&#x0436;&#x0438;&#x0442;&#x044C; &#x043A;&#x043E;&#x043D;&#x0441;&#x0443;&#x043B;&#x044C;&#x0442;&#x0430;&#x0446;&#x0438;&#x044E;
          </p>
          <button
            onClick={handleTopUp}
            className="rounded-full bg-tg-button px-8 py-3 text-lg font-semibold text-tg-button-text transition-transform active:scale-95"
          >
            &#x041F;&#x043E;&#x043F;&#x043E;&#x043B;&#x043D;&#x0438;&#x0442;&#x044C;
          </button>
        </div>
        {showPayment && (
          <PaymentModal
            apiBaseUrl={apiBaseUrl}
            sessionId={sessionId}
            onClose={() => setShowPayment(false)}
            onSuccess={handlePaymentSuccess}
          />
        )}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex flex-col bg-black">
      {/* Full-screen AI avatar background */}
      <div className="absolute inset-0 bg-gradient-to-b from-purple-900/30 via-black to-black" />

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
          className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`}
        />
        <span className="text-xs text-white/70">
          {isConnected ? '\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u043E' : '\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435...'}
        </span>
      </div>

      {/* Real-time pipeline status */}
      <div className="absolute inset-x-0 top-1/3 z-10 flex justify-center">
        <div className="rounded-full bg-black/40 px-5 py-2 backdrop-blur-sm">
          <p className="animate-pulse text-center text-sm font-medium text-white">
            {PIPELINE_STATUS_MAP[pipelineState]}
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
          aria-label={isMuted ? '\u0412\u043A\u043B\u044E\u0447\u0438\u0442\u044C \u043C\u0438\u043A\u0440\u043E\u0444\u043E\u043D' : '\u0412\u044B\u043A\u043B\u044E\u0447\u0438\u0442\u044C \u043C\u0438\u043A\u0440\u043E\u0444\u043E\u043D'}
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
          aria-label={'\u0417\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u044C \u0437\u0432\u043E\u043D\u043E\u043A'}
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
        <button
          onClick={handleTopUp}
          className="flex h-14 items-center rounded-full bg-white/20 px-4 backdrop-blur-sm"
        >
          <span className="text-sm font-semibold text-white">
            {formatBalance(balance)}
          </span>
        </button>
      </div>

      {/* Payment modal */}
      {showPayment && (
        <PaymentModal
          apiBaseUrl={apiBaseUrl}
          sessionId={sessionId}
          onClose={() => setShowPayment(false)}
          onSuccess={handlePaymentSuccess}
        />
      )}
    </div>
  );
}
