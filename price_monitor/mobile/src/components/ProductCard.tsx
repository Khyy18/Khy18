import React from 'react';
import {View, Text, Image, Pressable, StyleSheet} from 'react-native';
import {useTheme} from '../theme/ThemeContext';
import {Product} from '../types';
import {formatPrice} from '../utils/formatPrice';
import DiscountBadge from './DiscountBadge';
import SparklineChart from './SparklineChart';

interface ProductCardProps {
  product: Product;
  onPress: () => void;
}

const ProductCard: React.FC<ProductCardProps> = ({product, onPress}) => {
  const {colors} = useTheme();

  const last7Prices = product.priceHistory
    .slice(-7)
    .map(p => p.price);

  const marketplaceColor =
    product.marketplace === 'WB' ? '#A020F0' : '#005BFF';

  return (
    <Pressable
      onPress={onPress}
      style={[styles.card, {backgroundColor: colors.card}]}>
      <Image
        source={{uri: 'https://via.placeholder.com/300'}}
        style={styles.image}
        resizeMode="cover"
      />
      <View style={styles.content}>
        <View style={styles.topRow}>
          <View
            style={[
              styles.marketplaceBadge,
              {backgroundColor: marketplaceColor},
            ]}>
            <Text style={styles.marketplaceText}>{product.marketplace}</Text>
          </View>
          <DiscountBadge discount={product.discount} />
        </View>
        <Text
          style={[styles.title, {color: colors.text}]}
          numberOfLines={2}>
          {product.title}
        </Text>
        <View style={styles.priceRow}>
          <Text style={[styles.oldPrice, {color: colors.textSecondary}]}>
            {formatPrice(product.oldPrice)}
          </Text>
          <Text style={[styles.newPrice, {color: colors.primary}]}>
            {formatPrice(product.currentPrice)}
          </Text>
        </View>
        {last7Prices.length >= 2 && (
          <SparklineChart data={last7Prices} width={120} height={40} />
        )}
      </View>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  card: {
    borderRadius: 12,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.1,
    shadowRadius: 4,
    marginHorizontal: 16,
    marginVertical: 8,
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: 180,
  },
  content: {
    padding: 12,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  marketplaceBadge: {
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  marketplaceText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: 'bold',
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  oldPrice: {
    fontSize: 13,
    textDecorationLine: 'line-through',
    marginRight: 8,
  },
  newPrice: {
    fontSize: 16,
    fontWeight: 'bold',
  },
});

export default ProductCard;
