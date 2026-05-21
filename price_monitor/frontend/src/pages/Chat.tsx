import React, { useState, useRef, useEffect } from 'react';
import { useChatMessages, useSendMessage } from '../hooks/useApi';

export const Chat: React.FC = () => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { data: messages, isLoading } = useChatMessages();
  const sendMessage = useSendMessage();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || sendMessage.isPending) return;
    sendMessage.mutate(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="sticky top-0 bg-tg-bg px-4 py-3 border-b border-gray-100 z-10">
        <h1 className="text-lg font-bold text-tg-text">AI Помощник</h1>
        <p className="text-xs text-tg-hint">Спросите о товарах, ценах или скидках</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : messages && messages.length > 0 ? (
          messages.map((msg, index) => (
            <div
              key={msg.created_at + '-' + index}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm ${
                  msg.role === 'user'
                    ? 'bg-accent text-white rounded-tr-sm'
                    : 'bg-tg-secondary-bg text-tg-text rounded-tl-sm'
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-12">
            <p className="text-4xl mb-3">🤖</p>
            <p className="text-tg-hint text-sm">
              Привет! Я помогу найти лучшие скидки.<br />
              Спросите, например: &laquo;Где дешевле iPhone 15?&raquo;
            </p>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="sticky bottom-0 bg-tg-bg border-t border-gray-100 p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Задайте вопрос..."
            className="flex-1 px-4 py-2.5 bg-tg-secondary-bg rounded-full text-sm text-tg-text outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sendMessage.isPending}
            className="w-10 h-10 bg-accent text-white rounded-full flex items-center justify-center disabled:opacity-50"
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
};
