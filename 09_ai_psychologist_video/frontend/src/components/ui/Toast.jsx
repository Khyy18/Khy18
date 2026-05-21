import React, { createContext, useContext, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';

/**
 * @typedef {'info' | 'warning' | 'error'} ToastType
 * @typedef {{ id: number, message: string, type: ToastType }} ToastItem
 */

const ToastContext = createContext(null);

let toastId = 0;

/**
 * Хук для показа Toast-уведомлений.
 * @returns {{ showToast: (message: string, type?: ToastType) => void }}
 */
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

const typeStyles = {
  info: 'bg-blue-500 text-white',
  warning: 'bg-yellow-500 text-black',
  error: 'bg-red-500 text-white',
};

/**
 * Провайдер Toast-уведомлений. Оборачивает приложение.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = 'info') => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {createPortal(
        <div className="fixed top-4 left-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`pointer-events-auto rounded-xl px-4 py-3 shadow-lg font-medium text-sm animate-[slideIn_0.3s_ease-out] ${typeStyles[toast.type] || typeStyles.info}`}
              onClick={() => removeToast(toast.id)}
              style={{ animation: 'slideIn 0.3s ease-out' }}
            >
              {toast.message}
            </div>
          ))}
        </div>,
        document.body
      )}
      <style>{`
        @keyframes slideIn {
          from { transform: translateY(-20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
    </ToastContext.Provider>
  );
}
