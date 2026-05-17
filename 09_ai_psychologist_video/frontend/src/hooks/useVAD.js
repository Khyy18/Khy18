import { useState, useEffect, useRef } from 'react';

/**
 * Хук для Voice Activity Detection (VAD) на основе RMS-энергии аудио.
 * Определяет, говорит ли пользователь, и вызывает onSpeechEnd при паузе.
 * @param {MediaStream|null} stream - локальный медиапоток
 * @param {Object} options
 * @param {number} options.threshold - порог RMS энергии (0..1), default 0.01
 * @param {number} options.silenceTimeout - время тишины для срабатывания onSpeechEnd (мс), default 600
 * @param {function} options.onSpeechEnd - callback при окончании речи
 * @returns {{ isSpeaking }}
 */
export function useVAD(stream, { threshold = 0.01, silenceTimeout = 600, onSpeechEnd } = {}) {
  const [isSpeaking, setIsSpeaking] = useState(false);

  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const intervalRef = useRef(null);
  const silenceStartRef = useRef(null);
  const wasSpeakingRef = useRef(false);

  useEffect(() => {
    if (!stream) return;

    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) return;

    // Создание AudioContext и AnalyserNode
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    audioContextRef.current = audioContext;

    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyserRef.current = analyser;

    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    // Проверка RMS каждые 100мс
    intervalRef.current = setInterval(() => {
      analyser.getByteFrequencyData(dataArray);

      // Вычисление RMS энергии (нормализованное 0..1)
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const normalized = dataArray[i] / 255;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / dataArray.length);

      if (rms > threshold) {
        // Речь обнаружена
        silenceStartRef.current = null;
        if (!wasSpeakingRef.current) {
          wasSpeakingRef.current = true;
          setIsSpeaking(true);
        }
      } else {
        // Тишина
        if (wasSpeakingRef.current) {
          if (silenceStartRef.current === null) {
            silenceStartRef.current = Date.now();
          } else if (Date.now() - silenceStartRef.current >= silenceTimeout) {
            // Достаточно долгая тишина - речь закончилась
            wasSpeakingRef.current = false;
            setIsSpeaking(false);
            silenceStartRef.current = null;
            if (onSpeechEnd) {
              onSpeechEnd();
            }
          }
        }
      }
    }, 100);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      analyserRef.current = null;
      silenceStartRef.current = null;
      wasSpeakingRef.current = false;
    };
  }, [stream, threshold, silenceTimeout, onSpeechEnd]);

  return { isSpeaking };
}
