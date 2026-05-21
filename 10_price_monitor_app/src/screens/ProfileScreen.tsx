import React from 'react';
import {
  View,
  Text,
  ScrollView,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import {useQuery} from '@tanstack/react-query';
import {useNavigation} from '@react-navigation/native';
import {NativeStackNavigationProp} from '@react-navigation/native-stack';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';
import {getProfile} from '../api/services';
import {formatPrice} from '../utils/formatPrice';
import {RootStackParamList} from '../navigation/AppNavigator';

type ProfileNavProp = NativeStackNavigationProp<RootStackParamList>;

const ProfileScreen: React.FC = () => {
  const {colors} = useTheme();
  const navigation = useNavigation<ProfileNavProp>();

  const {data: profile, isLoading} = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
  });

  const copyReferralCode = () => {
    // In production would use Clipboard API
  };

  if (isLoading || !profile) {
    return (
      <View style={[styles.center, {backgroundColor: colors.background}]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const initials = profile.name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <ScrollView
      style={[styles.container, {backgroundColor: colors.background}]}
      contentContainerStyle={styles.content}>
      <View style={styles.avatarSection}>
        <View style={[styles.avatar, {backgroundColor: colors.primary}]}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
        <Text style={[styles.name, {color: colors.text}]}>{profile.name}</Text>
        <Text style={[styles.email, {color: colors.textSecondary}]}>
          {profile.email}
        </Text>
        <View
          style={[
            styles.subBadge,
            {
              backgroundColor:
                profile.subscription === 'vip' ? '#FFD700' : colors.border,
            },
          ]}>
          <Text
            style={[
              styles.subText,
              {
                color: profile.subscription === 'vip' ? '#1A1A2E' : colors.textSecondary,
              },
            ]}>
            {profile.subscription === 'vip' ? 'VIP' : 'Free'}
          </Text>
        </View>
      </View>

      <View style={styles.statsRow}>
        <View style={[styles.statCard, {backgroundColor: colors.card}]}>
          <Text style={[styles.statValue, {color: colors.primary}]}>
            {formatPrice(profile.totalSaved)}
          </Text>
          <Text style={[styles.statLabel, {color: colors.textSecondary}]}>
            Сэкономлено
          </Text>
        </View>
        <View style={[styles.statCard, {backgroundColor: colors.card}]}>
          <Text style={[styles.statValue, {color: colors.primary}]}>
            {profile.dealsTracked}
          </Text>
          <Text style={[styles.statLabel, {color: colors.textSecondary}]}>
            Отслежено
          </Text>
        </View>
        <View style={[styles.statCard, {backgroundColor: colors.card}]}>
          <Text style={[styles.statValue, {color: colors.primary}]}>
            {profile.bestDeal}%
          </Text>
          <Text style={[styles.statLabel, {color: colors.textSecondary}]}>
            Лучшая скидка
          </Text>
        </View>
      </View>

      <View style={[styles.referralSection, {backgroundColor: colors.card}]}>
        <Text style={[styles.sectionTitle, {color: colors.text}]}>
          Реферальный код
        </Text>
        <View style={styles.referralRow}>
          <Text style={[styles.referralCode, {color: colors.text}]}>
            {profile.referralCode}
          </Text>
          <Pressable onPress={copyReferralCode} style={styles.copyButton}>
            <MaterialCommunityIcons
              name="content-copy"
              size={20}
              color={colors.primary}
            />
            <Text style={[styles.copyText, {color: colors.primary}]}>
              Копировать
            </Text>
          </Pressable>
        </View>
      </View>

      <Pressable
        onPress={() => navigation.navigate('Settings')}
        style={[styles.settingsButton, {backgroundColor: colors.card}]}>
        <MaterialCommunityIcons name="cog" size={22} color={colors.text} />
        <Text style={[styles.settingsText, {color: colors.text}]}>
          Настройки
        </Text>
        <MaterialCommunityIcons
          name="chevron-right"
          size={22}
          color={colors.textSecondary}
        />
      </Pressable>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarSection: {
    alignItems: 'center',
    marginBottom: 24,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  avatarText: {
    color: '#FFFFFF',
    fontSize: 28,
    fontWeight: 'bold',
  },
  name: {
    fontSize: 20,
    fontWeight: 'bold',
  },
  email: {
    fontSize: 14,
    marginTop: 4,
  },
  subBadge: {
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 4,
    marginTop: 8,
  },
  subText: {
    fontSize: 12,
    fontWeight: 'bold',
  },
  statsRow: {
    flexDirection: 'row',
    marginBottom: 20,
  },
  statCard: {
    flex: 1,
    alignItems: 'center',
    padding: 12,
    marginHorizontal: 4,
    borderRadius: 12,
  },
  statValue: {
    fontSize: 14,
    fontWeight: 'bold',
  },
  statLabel: {
    fontSize: 11,
    marginTop: 4,
    textAlign: 'center',
  },
  referralSection: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
  },
  referralRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  referralCode: {
    fontSize: 16,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  copyText: {
    fontSize: 13,
    marginLeft: 4,
  },
  settingsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
  },
  settingsText: {
    flex: 1,
    fontSize: 16,
    marginLeft: 12,
  },
});

export default ProfileScreen;
