import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { topUp, applyPromo } from '../utils/api';

/**
 * Экран пополнения баланса.
 * Выбор суммы (пресеты или ввод вручную) и способа оплаты.
 */
export default function TopUp() {
  const navigate = useNavigate();
  const [amount, setAmount] = useState(300);
  const [customAmount, setCustomAmount] = useState('');
  const [method, setMethod] = useState(null); // 'stars' | 'card'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [promoCode, setPromoCode] = useState('');
  const [promoMessage, setPromoMessage] = useState(null);
  const [promoLoading, setPromoLoading] = useState(false);

  const presets = [100, 300, 500, 1000];

  function handlePresetClick(value) {
    setAmount(value);
    setCustomAmount('');
  }

  function handleCustomChange(e) {
    const val = e.target.value.replace(/\D/g, '');
    setCustomAmount(val);
    if (val) setAmount(Number(val));
  }

  async function handleConfirm() {
    if (!method) {
      setError('Выберите способ оплаты');
      return;
    }
    if (!amount || amount < 1) {
      setError('Укажите сумму');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await topUp(amount, method);
      navigate('/');
    } catch (err) {
      setError('Ошибка оплаты. Попробуйте позже.');
    } finally {
      setLoading(false);
    }
  }

  async function handleApplyPromo() {
    if (!promoCode.trim()) return;
    setPromoLoading(true);
    setPromoMessage(null);
    try {
      const result = await applyPromo(promoCode.trim());
      setPromoMessage({ success: true, text: result.message || 'Промокод применен!' });
      setPromoCode('');
    } catch (err) {
      const msg = err.data?.detail || 'Недействительный промокод';
      setPromoMessage({ success: false, text: msg });
    } finally {
      setPromoLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] p-4">
      {/* Навигация назад */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-[var(--tg-theme-button-color)] mb-4"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Назад
      </button>

      <h1 className="text-2xl font-bold mb-6">Пополнение баланса</h1>

      {/* Выбор суммы */}
      <div className="mb-6">
        <p className="text-[var(--tg-theme-hint-color)] text-sm mb-3">Сумма пополнения</p>
        <div className="grid grid-cols-4 gap-2 mb-3">
          {presets.map((preset) => (
            <button
              key={preset}
              onClick={() => handlePresetClick(preset)}
              className={`py-3 rounded-xl font-medium transition-colors ${
                amount === preset && !customAmount
                  ? 'bg-[var(--tg-theme-button-color)] text-white'
                  : 'bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
              }`}
            >
              {preset} &#8381;
            </button>
          ))}
        </div>
        <input
          type="text"
          inputMode="numeric"
          placeholder="Другая сумма"
          value={customAmount}
          onChange={handleCustomChange}
          className="w-full py-3 px-4 rounded-xl bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] placeholder-[var(--tg-theme-hint-color)] outline-none focus:ring-2 focus:ring-[var(--tg-theme-button-color)]"
        />
      </div>

      {/* Способ оплаты */}
      <div className="mb-6">
        <p className="text-[var(--tg-theme-hint-color)] text-sm mb-3">Способ оплаты</p>
        <div className="space-y-3">
          {/* Telegram Stars */}
          <button
            onClick={() => setMethod('stars')}
            className={`w-full flex items-center gap-3 p-4 rounded-xl transition-colors border-2 ${
              method === 'stars'
                ? 'border-[var(--tg-theme-button-color)] bg-[var(--tg-theme-button-color)]/10'
                : 'border-[var(--tg-theme-secondary-bg-color)] bg-[var(--tg-theme-secondary-bg-color)]'
            }`}
          >
            {/* Иконка звезды */}
            <div className="w-10 h-10 rounded-full bg-yellow-400 flex items-center justify-center flex-shrink-0">
              <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
              </svg>
            </div>
            <div className="text-left">
              <p className="font-medium">Telegram Stars</p>
              <p className="text-[var(--tg-theme-hint-color)] text-sm">Мгновенное пополнение</p>
            </div>
          </button>

          {/* Банковская карта (ЮKassa) */}
          <button
            onClick={() => setMethod('card')}
            className={`w-full flex items-center gap-3 p-4 rounded-xl transition-colors border-2 ${
              method === 'card'
                ? 'border-[var(--tg-theme-button-color)] bg-[var(--tg-theme-button-color)]/10'
                : 'border-[var(--tg-theme-secondary-bg-color)] bg-[var(--tg-theme-secondary-bg-color)]'
            }`}
          >
            {/* Иконка карты */}
            <div className="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center flex-shrink-0">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <div className="text-left">
              <p className="font-medium">Банковская карта</p>
              <p className="text-[var(--tg-theme-hint-color)] text-sm">ЮKassa</p>
            </div>
          </button>
        </div>
      </div>

      {/* Ошибка */}
      {error && (
        <p className="text-red-500 text-sm text-center mb-4">{error}</p>
      )}

      {/* Промокод */}
      <div className="mb-6">
        <p className="text-[var(--tg-theme-hint-color)] text-sm mb-3">Промокод</p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Введите промокод"
            value={promoCode}
            onChange={(e) => setPromoCode(e.target.value)}
            className="flex-1 py-3 px-4 rounded-xl bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] placeholder-[var(--tg-theme-hint-color)] outline-none focus:ring-2 focus:ring-[var(--tg-theme-button-color)]"
          />
          <button
            onClick={handleApplyPromo}
            disabled={promoLoading || !promoCode.trim()}
            className="px-4 py-3 rounded-xl bg-[var(--tg-theme-button-color)] text-white font-medium hover:opacity-90 disabled:opacity-50 transition-all"
          >
            {promoLoading ? '...' : 'Применить'}
          </button>
        </div>
        {promoMessage && (
          <p className={`text-sm mt-2 ${promoMessage.success ? 'text-green-500' : 'text-red-500'}`}>
            {promoMessage.text}
          </p>
        )}
      </div>

      {/* Кнопка подтверждения */}
      <button
        onClick={handleConfirm}
        disabled={loading || !method}
        className={`w-full py-4 rounded-xl text-white font-semibold text-lg transition-all ${
          method
            ? 'bg-[var(--tg-theme-button-color)] hover:opacity-90 active:scale-[0.98]'
            : 'bg-gray-400 cursor-not-allowed'
        }`}
      >
        {loading ? 'Обработка...' : `Пополнить на ${amount} ₽`}
      </button>
    </div>
  );
}
