import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Хук для захвата локального медиапотока (камера + микрофон).
 * Создает MediaRecorder для стриминга аудио-чанков через WebSocket.
 * @param {Object} options
 * @param {function} options.sendAudio - callback для отправки аудио-данных на сервер
 * @returns {{ localStream, startRecording, stopRecording, isRecording }}
 */
export function useMediaStream({ sendAudio } = {}) {
  const [localStream, setLocalStream] = useState(null);
  const [isRecording, setIsRecording] = useState(false);

  const streamRef = useRef(null);
  const recorderRef = useRef(null);

  // Запрос доступа к камере и микрофону при монтировании
  useEffect(() => {
    let cancelled = false;

    async function initMedia() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });
        if (!cancelled) {
          streamRef.current = stream;
          setLocalStream(stream);
        } else {
          // Если компонент размонтирован до получения стрима
          stream.getTracks().forEach((t) => t.stop());
        }
      } catch (err) {
        console.error('[useMediaStream] getUserMedia error:', err);
      }
    }

    initMedia();

    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop();
        recorderRef.current = null;
      }
      setLocalStream(null);
      setIsRecording(false);
    };
  }, []);

  // Начать запись и отправку аудио-чанков
  const startRecording = useCallback(() => {
    if (!streamRef.current || recorderRef.current) return;

    const mimeType = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      console.warn('[useMediaStream] mimeType not supported:', mimeType);
      return;
    }

    const recorder = new MediaRecorder(streamRef.current, { mimeType });
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0 && sendAudio) {
        sendAudio(event.data);
      }
    };

    recorder.start(250); // timeslice 250ms
    setIsRecording(true);
  }, [sendAudio]);

  // Остановить запись
  const stopRecording = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
      recorderRef.current = null;
      setIsRecording(false);
    }
  }, []);

  return { localStream, startRecording, stopRecording, isRecording };
}
