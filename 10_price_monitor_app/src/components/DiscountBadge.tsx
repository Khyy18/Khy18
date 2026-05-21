import React from 'react';
import {View, Text, StyleSheet} from 'react-native';

interface DiscountBadgeProps {
  discount: number;
}

const DiscountBadge: React.FC<DiscountBadgeProps> = ({discount}) => {
  return (
    <View style={styles.badge}>
      <Text style={styles.text}>-{discount}%</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    backgroundColor: '#E53935',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 4,
    alignSelf: 'flex-start',
  },
  text: {
    color: '#FFFFFF',
    fontWeight: 'bold',
    fontSize: 12,
  },
});

export default DiscountBadge;
