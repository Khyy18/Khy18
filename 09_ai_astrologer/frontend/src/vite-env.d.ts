/// <reference types="vite/client" />

interface TelegramWebApp {
  openLink: (url: string) => void;
  openInvoice: (url: string, callback?: (status: string) => void) => void;
  close: () => void;
  expand: () => void;
  ready: () => void;
  initData: string;
}

interface Window {
  Telegram?: {
    WebApp?: TelegramWebApp;
  };
}
