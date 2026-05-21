import WebApp from '@twa-dev/sdk';

export function useTelegram() {
  const tg = WebApp;

  const onClose = () => {
    tg.close();
  };

  const onMainButtonClick = (callback: () => void) => {
    tg.MainButton.onClick(callback);
  };

  const showMainButton = (text: string) => {
    tg.MainButton.setText(text);
    tg.MainButton.show();
  };

  const hideMainButton = () => {
    tg.MainButton.hide();
  };

  const showBackButton = () => {
    tg.BackButton.show();
  };

  const hideBackButton = () => {
    tg.BackButton.hide();
  };

  const onBackButtonClick = (callback: () => void) => {
    tg.BackButton.onClick(callback);
  };

  const hapticFeedback = (type: 'impact' | 'notification' | 'selection') => {
    if (type === 'impact') {
      tg.HapticFeedback.impactOccurred('medium');
    } else if (type === 'notification') {
      tg.HapticFeedback.notificationOccurred('success');
    } else {
      tg.HapticFeedback.selectionChanged();
    }
  };

  const ready = () => {
    tg.ready();
  };

  const expand = () => {
    tg.expand();
  };

  return {
    tg,
    user: tg.initDataUnsafe?.user,
    themeParams: tg.themeParams,
    colorScheme: tg.colorScheme,
    onClose,
    onMainButtonClick,
    showMainButton,
    hideMainButton,
    showBackButton,
    hideBackButton,
    onBackButtonClick,
    hapticFeedback,
    ready,
    expand,
  };
}
