import React from 'react';
import {View, Text, Switch, Pressable, StyleSheet} from 'react-native';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';
import {Alert} from '../types';
import {formatPrice} from '../utils/formatPrice';

interface AlertItemProps {
  alert: Alert;
  onToggle: (id: string, active: boolean) => void;
  onDelete?: (id: string) => void;
}

const AlertItem: React.FC<AlertItemProps> = ({alert, onToggle, onDelete}) => {
  const {colors} = useTheme();

  const formattedDate = new Date(alert.createdAt).toLocaleDateString('ru-RU');

  return (
    <View style={[styles.row, {backgroundColor: colors.card}]}>
      <View style={styles.info}>
        <Text style={[styles.keyword, {color: colors.text}]}>
          {alert.keyword}
        </Text>
        <Text style={[styles.details, {color: colors.textSecondary}]}>
          {formatPrice(alert.maxPrice)} | {alert.category}
        </Text>
        <Text style={[styles.date, {color: colors.textSecondary}]}>
          {formattedDate}
        </Text>
      </View>
      <Switch
        value={alert.active}
        onValueChange={value => onToggle(alert.id, value)}
        trackColor={{false: colors.border, true: colors.primary}}
        thumbColor="#FFFFFF"
      />
      {onDelete && (
        <Pressable
          onPress={() => onDelete(alert.id)}
          style={styles.deleteButton}>
          <MaterialCommunityIcons
            name="trash-can-outline"
            size={20}
            color={colors.error}
          />
        </Pressable>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    marginHorizontal: 16,
    marginVertical: 6,
    borderRadius: 12,
    elevation: 1,
  },
  info: {
    flex: 1,
  },
  keyword: {
    fontSize: 16,
    fontWeight: '600',
  },
  details: {
    fontSize: 13,
    marginTop: 4,
  },
  date: {
    fontSize: 11,
    marginTop: 4,
  },
  deleteButton: {
    marginLeft: 12,
    padding: 4,
  },
});

export default AlertItem;
