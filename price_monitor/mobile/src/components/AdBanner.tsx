import React from 'react';
import {View, Text, StyleSheet} from 'react-native';
import {useAds} from '../hooks/useAds';
import {ADS_CONFIG} from '../ads/config';

/**
 * Рекламный баннер (320x50)
 * Не показывается для VIP-пользователей
 * Placeholder, если SDK не инициализирован
 */
const AdBanner: React.FC = () => {
  const {shouldShowAds, adsReady} = useAds();

  if (!shouldShowAds) {
    return null;
  }

  // Placeholder пока SDK не полностью интегрирован
  return (
    <View style={styles.container}>
      {adsReady ? (
        <View style={styles.banner}>
          <Text style={styles.placeholderText}>Реклама</Text>
        </View>
      ) : (
        <View style={styles.banner}>
          <Text style={styles.placeholderText}>Загрузка...</Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    alignItems: 'center',
    backgroundColor: 'transparent',
  },
  banner: {
    width: ADS_CONFIG.bannerSize.width,
    height: ADS_CONFIG.bannerSize.height,
    backgroundColor: '#E8E8E8',
    borderRadius: 4,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  placeholderText: {
    color: '#999999',
    fontSize: 12,
  },
});

export default AdBanner;
