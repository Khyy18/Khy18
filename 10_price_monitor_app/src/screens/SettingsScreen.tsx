import React, {useState, useEffect} from 'react';
import {View, Text, Switch, ScrollView, StyleSheet} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {useTheme} from '../theme/ThemeContext';

const SETTINGS_KEY = '@price_monitor_settings';

interface Settings {
  pushNotifications: boolean;
  interests: Record<string, boolean>;
}

const defaultInterests: Record<string, boolean> = {
  electronics: true,
  clothing: true,
  home: true,
  kids: false,
  beauty: false,
  sports: false,
  auto: false,
  pets: false,
};

const categoryLabels: Record<string, string> = {
  electronics: 'Электроника',
  clothing: 'Одежда',
  home: 'Дом и сад',
  kids: 'Детские товары',
  beauty: 'Красота',
  sports: 'Спорт',
  auto: 'Авто',
  pets: 'Животные',
};

const SettingsScreen: React.FC = () => {
  const {colors, isDark, toggleTheme} = useTheme();
  const [pushNotifications, setPushNotifications] = useState(true);
  const [interests, setInterests] = useState<Record<string, boolean>>(
    defaultInterests,
  );

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const stored = await AsyncStorage.getItem(SETTINGS_KEY);
      if (stored) {
        const parsed: Settings = JSON.parse(stored);
        setPushNotifications(parsed.pushNotifications);
        setInterests(parsed.interests);
      }
    } catch (e) {
      // use defaults
    }
  };

  const saveSettings = async (updates: Partial<Settings>) => {
    const current: Settings = {
      pushNotifications,
      interests,
      ...updates,
    };
    try {
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(current));
    } catch (e) {
      // silent fail
    }
  };

  const handlePushToggle = (value: boolean) => {
    setPushNotifications(value);
    saveSettings({pushNotifications: value});
  };

  const handleInterestToggle = (key: string, value: boolean) => {
    const updated = {...interests, [key]: value};
    setInterests(updated);
    saveSettings({interests: updated});
  };

  return (
    <ScrollView
      style={[styles.container, {backgroundColor: colors.background}]}
      contentContainerStyle={styles.content}>
      <Text style={[styles.sectionHeader, {color: colors.textSecondary}]}>
        Уведомления
      </Text>
      <View style={[styles.row, {backgroundColor: colors.card}]}>
        <Text style={[styles.rowLabel, {color: colors.text}]}>
          Push-уведомления
        </Text>
        <Switch
          value={pushNotifications}
          onValueChange={handlePushToggle}
          trackColor={{false: colors.border, true: colors.primary}}
          thumbColor="#FFFFFF"
        />
      </View>

      <Text style={[styles.sectionHeader, {color: colors.textSecondary}]}>
        Интересы
      </Text>
      {Object.keys(interests).map(key => (
        <View
          key={key}
          style={[styles.row, {backgroundColor: colors.card}]}>
          <Text style={[styles.rowLabel, {color: colors.text}]}>
            {categoryLabels[key] || key}
          </Text>
          <Switch
            value={interests[key]}
            onValueChange={value => handleInterestToggle(key, value)}
            trackColor={{false: colors.border, true: colors.primary}}
            thumbColor="#FFFFFF"
          />
        </View>
      ))}

      <Text style={[styles.sectionHeader, {color: colors.textSecondary}]}>
        Оформление
      </Text>
      <View style={[styles.row, {backgroundColor: colors.card}]}>
        <Text style={[styles.rowLabel, {color: colors.text}]}>
          Темная тема
        </Text>
        <Switch
          value={isDark}
          onValueChange={toggleTheme}
          trackColor={{false: colors.border, true: colors.primary}}
          thumbColor="#FFFFFF"
        />
      </View>

      <Text style={[styles.sectionHeader, {color: colors.textSecondary}]}>
        О приложении
      </Text>
      <View style={[styles.row, {backgroundColor: colors.card}]}>
        <Text style={[styles.rowLabel, {color: colors.text}]}>
          Price Monitor
        </Text>
        <Text style={[styles.version, {color: colors.textSecondary}]}>
          1.0.0
        </Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingBottom: 32,
  },
  sectionHeader: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingHorizontal: 16,
    paddingTop: 20,
    paddingBottom: 8,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginHorizontal: 16,
    marginVertical: 2,
    borderRadius: 10,
  },
  rowLabel: {
    fontSize: 15,
  },
  version: {
    fontSize: 14,
  },
});

export default SettingsScreen;
