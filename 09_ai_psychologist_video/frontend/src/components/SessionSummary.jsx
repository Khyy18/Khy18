import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getSessionSummary } from '../utils/api';

/**
 * Преобразует mood_score (1-10) в эмодзи.
 */
function getMoodEmoji(score) {
  if (score <= 2) return '\u{1F622}'; // crying
  if (score <= 4) return '\u{1F614}'; // pensive
  if (score <= 6) return '\u{1F610}'; // neutral
  if (score <= 8) return '\u{1F642}'; // slightly smiling
  return '\u{1F60A}'; // smiling
}

/**
 * Экран итогов сессии.
 * Показывает длительность, стоимость, резюме, домашнее задание, оценку настроения.
 */
export default function SessionSummary() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadSummary();
  }, [sessionId]);

  async function loadSummary() {
    setLoading(true);
    setError(null);
    try {
      const result = await getSessionSummary(sessionId);
      setData(result);
    } catch (err) {
      setError('Не удалось загрузить итоги сессии');
    } finally {
      setLoading(false);
    }
  }

  function formatDuration(seconds) {
    if (!seconds) return '0 мин';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m === 0) return `${s} сек`;
    return `${m} мин ${s > 0 ? `${s} сек` : ''}`;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--tg-theme-bg-color)]">
        <div className="animate-spin w-8 h-8 border-4 border-[var(--tg-theme-button-color)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] flex flex-col items-center justify-center p-4">
        <p className="text-red-500 mb-4">{error}</p>
        <button
          onClick={loadSummary}
          className="px-6 py-3 rounded-xl bg-[var(--tg-theme-button-color)] text-white font-medium"
        >
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] p-4 pb-8">
      <h1 className="text-2xl font-bold text-center mb-6">Итоги сессии</h1>

      {/* Статистика */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 text-center">
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Длительность</p>
          <p className="font-bold text-lg">{formatDuration(data?.duration)}</p>
        </div>
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 text-center">
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Стоимость</p>
          <p className="font-bold text-lg">{data?.cost || 0} &#8381;</p>
        </div>
      </div>

      {/* Оценка настроения */}
      {data?.mood_score != null && (
        <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4 mb-6 text-center">
          <p className="text-[var(--tg-theme-hint-color)] text-xs mb-1">Настроение</p>
          <p className="text-3xl mb-1">{getMoodEmoji(data.mood_score)}</p>
          <p className="font-medium">{data.mood_score}/10</p>
        </div>
      )}

      {/* Резюме */}
      {data?.summary && (
        <div className="mb-6">
          <h2 className="font-semibold text-lg mb-2">Резюме</h2>
          <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{data.summary}</p>
          </div>
        </div>
      )}

      {/* Домашнее задание */}
      {data?.homework && (
        <div className="mb-6">
          <h2 className="font-semibold text-lg mb-2">Домашнее задание</h2>
          <div className="bg-[var(--tg-theme-secondary-bg-color)] rounded-xl p-4">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{data.homework}</p>
          </div>
        </div>
      )}

      {/* Кнопка возврата */}
      <button
        onClick={() => navigate('/')}
        className="w-full py-4 rounded-xl bg-[var(--tg-theme-button-color)] text-white font-semibold text-lg hover:opacity-90 active:scale-[0.98] transition-all"
      >
        Вернуться
      </button>
    </div>
  );
}
