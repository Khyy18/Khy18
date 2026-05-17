/// <reference types="vite/client" />

interface TelegramWebApp {
  openLink: (url: string) => void;
  close: () => void;
  expand: () => void;
  ready: () => void;
}

interface Window {
  Telegram?: {
    WebApp?: TelegramWebApp;
  };
}
