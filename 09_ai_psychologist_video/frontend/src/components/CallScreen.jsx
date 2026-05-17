import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket';
import { useMediaStream } from '../hooks/useMediaStream';
import { useLiveKit } from '../hooks/useLiveKit';
import { useVAD } from '../hooks/useVAD';

/**
 * Экран видеозвонка с AI-психологом.
 * Полноэкранный layout с видео аватара, PiP локальной камеры,
 * таймером, балансом, индикатором статуса и кнопками управления.
 */
export default function CallScreen() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { status, sendAudio, sendControl, lastMessage, isConnected } = useWebSocket(sessionId);

  const [isMuted, setIsMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [balance, setBalance] = useState(0);
  const [aiStatus, setAiStatus] = useState('listening'); // listening | thinking | speaking
  const [livekitToken, setLivekitToken] = useState(null);
  const [livekitUrl, setLivekitUrl] = useState(null);

  const avatarVideoRef = useRef(null);
  const localVideoRef = useRef(null);
  const timerRef = useRef(null);

  // Локальный медиапоток: камера + микрофон + стриминг аудио
  const { localStream, startRecording, stopRecording } = useMediaStream({ sendAudio });

  // VAD: определение активности речи
  const handleSpeechEnd = useCallback(() => {
    // Можно отправить контрольный сигнал серверу о конце фразы
    sendControl({ action: 'speech_end' });
  }, [sendControl]);

  const { isSpeaking } = useVAD(localStream, {
    threshold: 0.01,
    silenceTimeout: 600,
    onSpeechEnd: handleSpeechEnd,
  });

  // LiveKit: удаленное видео аватара
  const { remoteVideoTrack, isConnected: livekitConnected } = useLiveKit({
    token: livekitToken,
    serverUrl: livekitUrl,
  });

  // Привязка локального стрима к PiP-видео
  useEffect(() => {
    if (localVideoRef.current && localStream) {
      localVideoRef.current.srcObject = localStream;
    }
  }, [localStream]);

  // Привязка удаленного LiveKit видео к аватар-элементу
  useEffect(() => {
    if (avatarVideoRef.current && remoteVideoTrack) {
      remoteVideoTrack.attach(avatarVideoRef.current);
      return () => {
        remoteVideoTrack.detach(avatarVideoRef.current);
      };
    }
  }, [remoteVideoTrack]);

  // Начать запись аудио когда WebSocket подключен
  useEffect(() => {
    if (isConnected && localStream) {
      startRecording();
    }
    return () => {
      stopRecording();
    };
  }, [isConnected, localStream, startRecording, stopRecording]);

  // Таймер сессии - считает с 00:00 вверх
  useEffect(() => {
    if (isConnected) {
      timerRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isConnected]);

  // Обработка входящих сообщений от сервера
  useEffect(() => {
    if (!lastMessage) return;

    if (lastMessage.type === 'status') {
      setAiStatus(lastMessage.state || 'listening');
    } else if (lastMessage.type === 'balance_update') {
      setBalance(lastMessage.balance);
    } else if (lastMessage.type === 'session_ended') {
      navigate('/');
    } else if (lastMessage.type === 'livekit_token') {
      // Сервер может прислать LiveKit токен через WebSocket
      setLivekitToken(lastMessage.token);
      setLivekitUrl(lastMessage.url);
    }
  }, [lastMessage, navigate]);

  // Форматирование времени в MM:SS
  function formatTime(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  // Текст статуса AI на русском
  function getStatusText() {
    if (isSpeaking) return 'Психолог слушает...';
    switch (aiStatus) {
      case 'thinking': return 'Психолог думает...';
      case 'speaking': return 'Психолог говорит...';
      default: return 'Психолог слушает...';
    }
  }

  function handleMuteToggle() {
    const newMuted = !isMuted;
    setIsMuted(newMuted);
    // Отключение/включение аудио-трека
    if (localStream) {
      const audioTracks = localStream.getAudioTracks();
      if (audioTracks.length > 0) {
        audioTracks[0].enabled = !newMuted;
      }
    }
    sendControl({ action: newMuted ? 'mute' : 'unmute' });
  }

  function handleEndCall() {
    // Остановка всех треков медиапотока
    if (localStream) {
      localStream.getTracks().forEach((t) => t.stop());
    }
    stopRecording();
    sendControl({ action: 'end_call' });
    navigate('/');
  }

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-black">
      {/* Основное видео AI-аватара - полноэкранный фон */}
      <video
        ref={avatarVideoRef}
        className="absolute inset-0 w-full h-full object-cover"
        autoPlay
        playsInline
        muted
      />

      {/* PiP - локальная камера (120x160, нижний правый угол) */}
      <div className="absolute bottom-24 right-4 w-[120px] h-[160px] rounded-xl overflow-hidden shadow-lg border-2 border-white/30 z-10">
        <video
          ref={localVideoRef}
          className="w-full h-full object-cover"
          autoPlay
          playsInline
          muted
        />
      </div>

      {/* Верхняя панель: таймер + баланс */}
      <div className="absolute top-0 left-0 right-0 flex justify-between items-center px-4 py-3 bg-gradient-to-b from-black/60 to-transparent z-10">
        <div className="text-white font-mono text-lg">
          {formatTime(elapsed)}
        </div>
        <div className="text-white font-medium">
          {balance} &#8381;
        </div>
      </div>

      {/* Индикатор статуса AI */}
      <div className="absolute top-14 left-0 right-0 flex justify-center z-10">
        <div className="flex items-center gap-2 bg-black/40 backdrop-blur-sm rounded-full px-4 py-2">
          {/* Пульсирующая точка */}
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
          </span>
          <span className="text-white text-sm">{getStatusText()}</span>
        </div>
      </div>

      {/* Нижняя панель управления */}
      <div className="absolute bottom-0 left-0 right-0 flex justify-center items-center gap-8 pb-8 pt-4 bg-gradient-to-t from-black/60 to-transparent z-10">
        {/* Кнопка мьют (микрофон) */}
        <button
          onClick={handleMuteToggle}
          className={`w-14 h-14 rounded-full flex items-center justify-center transition-colors ${
            isMuted ? 'bg-red-500/80' : 'bg-white/20 backdrop-blur-sm'
          }`}
        >
          {isMuted ? (
            // Микрофон перечеркнут
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 19L5 5m0 0l14 14M12 18.75a6 6 0 01-6-6v-1.5m6 7.5a6 6 0 006-6v-1.5m-6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
            </svg>
          ) : (
            // Микрофон активен
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
            </svg>
          )}
        </button>

        {/* Кнопка завершения звонка */}
        <button
          onClick={handleEndCall}
          className="w-16 h-16 rounded-full bg-red-600 flex items-center justify-center shadow-lg hover:bg-red-700 transition-colors"
        >
          {/* Иконка трубки (phone-down) */}
          <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15.536a5 5 0 001.414 1.414m2.828-9.9a9 9 0 0112.728 0M3.75 20.25l16.5-16.5" />
          </svg>
        </button>
      </div>

      {/* Оверлей при подключении */}
      {!isConnected && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70 z-20">
          <div className="text-center">
            <div className="animate-spin w-10 h-10 border-4 border-white border-t-transparent rounded-full mx-auto mb-4" />
            <p className="text-white text-lg">Подключение...</p>
          </div>
        </div>
      )}
    </div>
  );
}
