/**
 * Конфигурация рекламных SDK
 * Тестовые Ad Unit IDs для разработки
 */

// Google AdMob Test IDs
export const ADMOB_APP_ID = 'ca-app-pub-3940256099942544~3347511713'; // Test App ID

export const AD_UNITS = {
  // Google AdMob test ad units
  admob: {
    banner: 'ca-app-pub-3940256099942544/6300978111',
    interstitial: 'ca-app-pub-3940256099942544/1033173712',
    rewarded: 'ca-app-pub-3940256099942544/5224354917',
  },
  // Yandex Mobile Ads test ad units
  yandex: {
    banner: 'R-M-DEMO-320x50',
    interstitial: 'R-M-DEMO-interstitial',
    rewarded: 'R-M-DEMO-rewarded-client-side-rtb',
  },
};

export const ADS_CONFIG = {
  /** Показывать interstitial каждые N карточек в ленте */
  interstitialFrequency: 5,
  /** Позиция баннера */
  bannerPosition: 'bottom' as const,
  /** Размер баннера */
  bannerSize: {width: 320, height: 50},
  /** Длительность VIP за просмотр rewarded video (в часах) */
  rewardedVipDurationHours: 1,
};
