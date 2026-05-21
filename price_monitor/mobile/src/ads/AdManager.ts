/**
 * Менеджер рекламы
 * Управляет показом баннеров, interstitial и rewarded video
 * Проверяет VIP-статус перед показом
 */

import {AD_UNITS, ADS_CONFIG} from './config';

type AdProvider = 'admob' | 'yandex';

interface AdManagerState {
  initialized: boolean;
  provider: AdProvider;
  interstitialReady: boolean;
  rewardedReady: boolean;
  interstitialCount: number;
}

class AdManagerClass {
  private state: AdManagerState = {
    initialized: false,
    provider: 'admob',
    interstitialReady: false,
    rewardedReady: false,
    interstitialCount: 0,
  };

  private isVip: boolean = false;

  /**
   * Инициализация рекламного SDK
   */
  async initialize(provider: AdProvider = 'admob'): Promise<void> {
    this.state.provider = provider;
    this.state.initialized = true;
    // В продакшене здесь будет вызов MobileAds().initialize()
    console.log(`[AdManager] Initialized with provider: ${provider}`);
    await this.preloadInterstitial();
    await this.preloadRewarded();
  }

  /**
   * Установить VIP-статус пользователя
   */
  setVipStatus(isVip: boolean): void {
    this.isVip = isVip;
  }

  /**
   * Проверить, нужно ли показывать рекламу
   */
  shouldShowAds(): boolean {
    return !this.isVip && this.state.initialized;
  }

  /**
   * Получить ID рекламного блока для текущего провайдера
   */
  getAdUnitId(type: 'banner' | 'interstitial' | 'rewarded'): string {
    return AD_UNITS[this.state.provider][type];
  }

  /**
   * Показать баннер (возвращает данные для рендера)
   */
  showBanner(): {unitId: string; size: {width: number; height: number}} | null {
    if (!this.shouldShowAds()) {
      return null;
    }
    return {
      unitId: this.getAdUnitId('banner'),
      size: ADS_CONFIG.bannerSize,
    };
  }

  /**
   * Показать interstitial рекламу
   */
  async showInterstitial(): Promise<boolean> {
    if (!this.shouldShowAds()) {
      return false;
    }

    this.state.interstitialCount++;

    if (this.state.interstitialCount % ADS_CONFIG.interstitialFrequency !== 0) {
      return false;
    }

    if (!this.state.interstitialReady) {
      await this.preloadInterstitial();
    }

    // В продакшене здесь будет вызов InterstitialAd.show()
    console.log('[AdManager] Showing interstitial ad');
    this.state.interstitialReady = false;
    await this.preloadInterstitial();
    return true;
  }

  /**
   * Показать rewarded video
   */
  async showRewarded(onReward: () => void): Promise<boolean> {
    if (!this.state.initialized) {
      return false;
    }

    if (!this.state.rewardedReady) {
      await this.preloadRewarded();
    }

    // В продакшене здесь будет вызов RewardedAd.show()
    console.log('[AdManager] Showing rewarded ad');
    this.state.rewardedReady = false;

    // Симуляция просмотра рекламы (в проде - callback от SDK)
    onReward();
    await this.preloadRewarded();
    return true;
  }

  /**
   * Предзагрузка interstitial
   */
  private async preloadInterstitial(): Promise<void> {
    // В продакшене: InterstitialAd.createForAdRequest(unitId).load()
    this.state.interstitialReady = true;
  }

  /**
   * Предзагрузка rewarded video
   */
  private async preloadRewarded(): Promise<void> {
    // В продакшене: RewardedAd.createForAdRequest(unitId).load()
    this.state.rewardedReady = true;
  }

  /**
   * Проверить, инициализирован ли SDK
   */
  isInitialized(): boolean {
    return this.state.initialized;
  }

  /**
   * Сбросить счетчик interstitial (например, при смене экрана)
   */
  resetInterstitialCount(): void {
    this.state.interstitialCount = 0;
  }
}

export const AdManager = new AdManagerClass();
