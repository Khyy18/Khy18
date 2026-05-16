import React from 'react';
import {Pressable, Text, StyleSheet} from 'react-native';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';

interface CategoryCardProps {
  name: string;
  icon: string;
  productCount: number;
  onPress: () => void;
}

const CategoryCard: React.FC<CategoryCardProps> = ({
  name,
  icon,
  productCount,
  onPress,
}) => {
  const {colors} = useTheme();

  return (
    <Pressable
      onPress={onPress}
      style={[styles.card, {backgroundColor: colors.card}]}>
      <MaterialCommunityIcons name={icon} size={36} color={colors.primary} />
      <Text style={[styles.name, {color: colors.text}]}>{name}</Text>
      <Text style={[styles.count, {color: colors.textSecondary}]}>
        {productCount} товаров
      </Text>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  card: {
    flex: 1,
    margin: 8,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 1},
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  name: {
    fontSize: 13,
    fontWeight: '600',
    marginTop: 8,
    textAlign: 'center',
  },
  count: {
    fontSize: 11,
    marginTop: 4,
  },
});

export default CategoryCard;
