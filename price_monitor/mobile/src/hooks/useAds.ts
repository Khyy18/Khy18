import {useState, useEffect, useCallback} from 'react';
import {useQuery} from '@tanstack/react-query';
import {getProfile} from '../api/services';
import {AdManager} from '../ads/AdManager';

/**
 * Hook для управления рекламой
 * Проверяет VIP-статус и контролирует показ рекламы
 */
export const useAds = () => {
  const [adsReady, setAdsReady] = useState(false);

  const {data: profile} = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
  });

  const isVip = profile?.subscription === 'vip';

  useEffect(() => {
    AdManager.setVipStatus(isVip);
  }, [isVip]);

  useEffect(() => {
    const init = async () => {
      if (!AdManager.isInitialized()) {
        await AdManager.initialize('admob');
      }
      setAdsReady(true);
    };
    init();
  }, []);

  const shouldShowAds = !isVip && adsReady;

  return {
    shouldShowAds,
    isVip,
    adsReady,
  };
};

/**
 * Hook для загрузки и показа interstitial
 */
export const useInterstitialAd = () => {
  const {shouldShowAds} = useAds();

  const showInterstitial = useCallback(async (): Promise<boolean> => {
    if (!shouldShowAds) {
      return false;
    }
    return AdManager.showInterstitial();
  }, [shouldShowAds]);

  return {
    showInterstitial,
    shouldShowAds,
  };
};

/**
 * Hook для rewarded video
 */
export const useRewardedAd = () => {
  const [isLoading, setIsLoading] = useState(false);

  const showRewarded = useCallback(async (onReward: () => void): Promise<boolean> => {
    setIsLoading(true);
    try {
      const result = await AdManager.showRewarded(onReward);
      return result;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    showRewarded,
    isLoading,
  };
};
