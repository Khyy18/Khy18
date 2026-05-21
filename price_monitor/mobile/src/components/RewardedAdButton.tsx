import React from 'react';
import {Pressable, Text, ActivityIndicator, StyleSheet} from 'react-native';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useRewardedAd} from '../hooks/useAds';

interface RewardedAdButtonProps {
  onReward: () => void;
}

/**
 * Кнопка "Смотреть рекламу - 1 час VIP бесплатно"
 * Показывает rewarded video, после просмотра вызывает callback
 */
const RewardedAdButton: React.FC<RewardedAdButtonProps> = ({onReward}) => {
  const {showRewarded, isLoading} = useRewardedAd();

  const handlePress = async () => {
    await showRewarded(onReward);
  };

  return (
    <Pressable
      onPress={handlePress}
      disabled={isLoading}
      style={({pressed}) => [
        styles.button,
        pressed && styles.buttonPressed,
        isLoading && styles.buttonDisabled,
      ]}>
      {isLoading ? (
        <ActivityIndicator size="small" color="#FFFFFF" />
      ) : (
        <>
          <MaterialCommunityIcons name="play-circle" size={20} color="#FFFFFF" />
          <Text style={styles.buttonText}>
            Смотри рекламу — получи VIP на 1 час
          </Text>
        </>
      )}
    </Pressable>
  );
};

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FF6B35',
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 20,
    gap: 8,
  },
  buttonPressed: {
    opacity: 0.85,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
});

export default RewardedAdButton;
