import React, {useState, useCallback} from 'react';
import {
  View,
  Text,
  Image,
  ScrollView,
  Pressable,
  Modal,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import {useQuery} from '@tanstack/react-query';
import {RouteProp, useRoute} from '@react-navigation/native';
import {WebView} from 'react-native-webview';
import type {ShouldStartLoadRequest} from 'react-native-webview/lib/WebViewTypes';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';
import {useFavorites} from '../hooks/useFavorites';
import {getDealById} from '../api/services';
import {formatPrice} from '../utils/formatPrice';
import PriceChart from '../components/PriceChart';
import DiscountBadge from '../components/DiscountBadge';
import {RootStackParamList} from '../navigation/AppNavigator';

const ALLOWED_DOMAINS = ['wildberries.ru', 'ozon.ru'];

const isAllowedUrl = (url: string): boolean => {
  try {
    const hostname = new URL(url).hostname;
    return ALLOWED_DOMAINS.some(
      domain => hostname === domain || hostname.endsWith('.' + domain),
    );
  } catch {
    return false;
  }
};

type DetailRouteProp = RouteProp<RootStackParamList, 'ProductDetail'>;

const ProductDetailScreen: React.FC = () => {
  const {colors} = useTheme();
  const route = useRoute<DetailRouteProp>();
  const {productId} = route.params;
  const {isFavorite, toggleFavorite} = useFavorites();
  const [webViewVisible, setWebViewVisible] = useState(false);

  const handleShouldStartLoad = useCallback((event: ShouldStartLoadRequest): boolean => {
    return isAllowedUrl(event.url);
  }, []);

  const {data: product, isLoading} = useQuery({
    queryKey: ['product', productId],
    queryFn: () => getDealById(productId),
  });

  if (isLoading) {
    return (
      <View style={[styles.center, {backgroundColor: colors.background}]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!product) {
    return (
      <View style={[styles.center, {backgroundColor: colors.background}]}>
        <Text style={{color: colors.text}}>Товар не найден</Text>
      </View>
    );
  }

  const favorite = isFavorite(product.id);
  const marketplaceColor =
    product.marketplace === 'WB' ? '#A020F0' : '#005BFF';

  return (
    <View style={[styles.container, {backgroundColor: colors.background}]}>
      <ScrollView>
        <Image
          source={{uri: 'https://via.placeholder.com/400'}}
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
              <Text style={styles.marketplaceText}>
                {product.marketplace}
              </Text>
            </View>
            <DiscountBadge discount={product.discount} />
          </View>

          <Text style={[styles.title, {color: colors.text}]}>
            {product.title}
          </Text>

          <View style={styles.priceSection}>
            <Text style={[styles.oldPrice, {color: colors.textSecondary}]}>
              {formatPrice(product.oldPrice)}
            </Text>
            <Text style={[styles.currentPrice, {color: colors.primary}]}>
              {formatPrice(product.currentPrice)}
            </Text>
          </View>

          <View style={styles.chartSection}>
            <Text style={[styles.sectionTitle, {color: colors.text}]}>
              История цены
            </Text>
            <PriceChart priceHistory={product.priceHistory} />
          </View>

          <View style={styles.section}>
            <Text style={[styles.sectionTitle, {color: colors.text}]}>
              Саммари отзывов
            </Text>
            <Text style={[styles.reviewText, {color: colors.textSecondary}]}>
              {product.reviewsSummary}
            </Text>
          </View>

          <View style={styles.ratingRow}>
            <MaterialCommunityIcons
              name="star"
              size={20}
              color="#FFD700"
            />
            <Text style={[styles.ratingText, {color: colors.text}]}>
              {product.rating.toFixed(1)}
            </Text>
          </View>

          <View style={styles.actions}>
            <Pressable
              onPress={() => toggleFavorite(product.id)}
              style={[
                styles.favButton,
                {borderColor: colors.primary},
              ]}>
              <MaterialCommunityIcons
                name={favorite ? 'heart' : 'heart-outline'}
                size={20}
                color={colors.primary}
              />
              <Text style={[styles.favButtonText, {color: colors.primary}]}>
                {favorite ? 'В избранном' : 'В избранное'}
              </Text>
            </Pressable>

            <Pressable
              onPress={() => setWebViewVisible(true)}
              style={[styles.buyButton, {backgroundColor: colors.primary}]}>
              <Text style={styles.buyButtonText}>Купить</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>

      <Modal
        visible={webViewVisible}
        animationType="slide"
        onRequestClose={() => setWebViewVisible(false)}>
        <View style={styles.webViewContainer}>
          <Pressable
            onPress={() => setWebViewVisible(false)}
            style={[styles.closeButton, {backgroundColor: colors.card}]}>
            <MaterialCommunityIcons
              name="close"
              size={24}
              color={colors.text}
            />
          </Pressable>
          <WebView
            source={{uri: product.affiliateUrl}}
            originWhitelist={['https://*.wildberries.ru', 'https://*.ozon.ru', 'https://wildberries.ru', 'https://ozon.ru']}
            onShouldStartLoadWithRequest={handleShouldStartLoad}
            style={styles.webView}
          />
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  image: {
    width: '100%',
    height: 300,
  },
  content: {
    padding: 16,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  marketplaceBadge: {
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  marketplaceText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: 'bold',
  },
  title: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  priceSection: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  oldPrice: {
    fontSize: 16,
    textDecorationLine: 'line-through',
    marginRight: 12,
  },
  currentPrice: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  chartSection: {
    marginBottom: 20,
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
  },
  reviewText: {
    fontSize: 14,
    lineHeight: 20,
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  ratingText: {
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 6,
  },
  actions: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 32,
  },
  favButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 2,
  },
  favButtonText: {
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 6,
  },
  buyButton: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 12,
  },
  buyButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
  },
  webViewContainer: {
    flex: 1,
  },
  closeButton: {
    padding: 12,
    alignItems: 'flex-end',
  },
  webView: {
    flex: 1,
  },
});

export default ProductDetailScreen;
