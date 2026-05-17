import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const slides = [
  {
    title: 'AI Психолог',
    description:
      'Это ваш персональный AI-психолог, доступный 24/7 через видеозвонок. Получайте поддержку и рекомендации в любое удобное время.',
    icon: (
      <svg className="w-20 h-20 text-purple-500" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
      </svg>
    ),
  },
  {
    title: 'Как это работает',
    description:
      'Вы начинаете голосовой звонок с AI-психологом. Оплата поминутная - вы платите только за время разговора. Все данные конфиденциальны.',
    icon: (
      <svg className="w-20 h-20 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
      </svg>
    ),
  },
  {
    title: 'Важно знать',
    description:
      'AI Психолог не заменяет реального специалиста. При серьезных проблемах обращайтесь к лицензированному психологу или психотерапевту. Это инструмент поддержки и самопомощи.',
    icon: (
      <svg className="w-20 h-20 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
    ),
  },
];

/**
 * Экран онбординга. 3 слайда с информацией.
 * Показывается при первом запуске (если нет localStorage 'onboarding_complete').
 */
export default function Onboarding() {
  const navigate = useNavigate();
  const [currentSlide, setCurrentSlide] = useState(0);

  function handleNext() {
    if (currentSlide < slides.length - 1) {
      setCurrentSlide(currentSlide + 1);
    } else {
      localStorage.setItem('onboarding_complete', 'true');
      navigate('/');
    }
  }

  const isLast = currentSlide === slides.length - 1;

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] flex flex-col items-center justify-between p-6">
      {/* Контент слайда */}
      <div className="flex-1 flex flex-col items-center justify-center text-center max-w-sm">
        <div className="mb-8">{slides[currentSlide].icon}</div>
        <h1 className="text-2xl font-bold mb-4">{slides[currentSlide].title}</h1>
        <p className="text-[var(--tg-theme-hint-color)] text-base leading-relaxed">
          {slides[currentSlide].description}
        </p>
      </div>

      {/* Нижняя часть: точки + кнопка */}
      <div className="w-full max-w-sm">
        {/* Индикатор слайдов */}
        <div className="flex justify-center gap-2 mb-6">
          {slides.map((_, idx) => (
            <div
              key={idx}
              className={`w-2.5 h-2.5 rounded-full transition-colors ${
                idx === currentSlide
                  ? 'bg-[var(--tg-theme-button-color)]'
                  : 'bg-[var(--tg-theme-hint-color)]/30'
              }`}
            />
          ))}
        </div>

        {/* Кнопка */}
        <button
          onClick={handleNext}
          className="w-full py-4 rounded-xl bg-[var(--tg-theme-button-color)] text-white font-semibold text-lg hover:opacity-90 active:scale-[0.98] transition-all"
        >
          {isLast ? 'Начать' : 'Далее'}
        </button>
      </div>
    </div>
  );
}
