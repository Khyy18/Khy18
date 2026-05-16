import React, {useRef} from 'react';
import {
  View,
  FlatList,
  ActivityIndicator,
  RefreshControl,
  Text,
  Pressable,
  StyleSheet,
} from 'react-native';
import {useInfiniteQuery} from '@tanstack/react-query';
import {useNavigation, useRoute, RouteProp} from '@react-navigation/native';
import {NativeStackNavigationProp} from '@react-navigation/native-stack';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';
import {getDeals} from '../api/services';
import {Product} from '../types';
import ProductCard from '../components/ProductCard';
import EmptyState from '../components/EmptyState';
import AdBanner from '../components/AdBanner';
import {useAds, useInterstitialAd} from '../hooks/useAds';
import {ADS_CONFIG} from '../ads/config';
import {RootStackParamList, TabParamList} from '../navigation/AppNavigator';

type FeedNavProp = NativeStackNavigationProp<RootStackParamList>;
type FeedRouteProp = RouteProp<TabParamList, 'Feed'>;

type FeedListItem =
  | {type: 'product'; data: Product}
  | {type: 'ad'; id: string};

const FeedScreen: React.FC = () => {
  const {colors, toggleTheme, isDark} = useTheme();
  const navigation = useNavigation<FeedNavProp>();
  const route = useRoute<FeedRouteProp>();
  const category = (route.params as {category?: string} | undefined)?.category;
  const {shouldShowAds} = useAds();
  const {showInterstitial} = useInterstitialAd();
  const itemViewedCount = useRef(0);

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    refetch,
    isRefetching,
  } = useInfiniteQuery({
    queryKey: ['deals', category],
    queryFn: ({pageParam}) => getDeals(pageParam as number, 10, category),
    initialPageParam: 1,
    getNextPageParam: (lastPage, _allPages, lastPageParam) => {
      if (lastPage.hasMore) {
        return (lastPageParam as number) + 1;
      }
      return undefined;
    },
  });

  const allProducts: Product[] =
    data?.pages.flatMap(page => page.products) ?? [];

  // Вставляем рекламные разделители каждые N элементов
  const feedItems: FeedListItem[] = [];
  allProducts.forEach((product, index) => {
    feedItems.push({type: 'product', data: product});
    if (
      shouldShowAds &&
      (index + 1) % ADS_CONFIG.interstitialFrequency === 0
    ) {
      feedItems.push({type: 'ad', id: `ad-${index}`});
    }
  });

  const handleEndReached = () => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  };

  const handleProductPress = (productId: string) => {
    itemViewedCount.current++;
    if (
      shouldShowAds &&
      itemViewedCount.current % ADS_CONFIG.interstitialFrequency === 0
    ) {
      showInterstitial();
    }
    navigation.navigate('ProductDetail', {productId});
  };

  const renderItem = ({item}: {item: FeedListItem}) => {
    if (item.type === 'ad') {
      return (
        <View style={styles.adDivider}>
          <Text style={styles.adDividerText}>Реклама</Text>
        </View>
      );
    }
    return (
      <ProductCard
        product={item.data}
        onPress={() => handleProductPress(item.data.id)}
      />
    );
  };

  const renderFooter = () => {
    if (!isFetchingNextPage) {
      return null;
    }
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  };

  return (
    <View style={[styles.container, {backgroundColor: colors.background}]}>
      <View style={[styles.header, {backgroundColor: colors.card}]}>
        <Text style={[styles.headerTitle, {color: colors.text}]}>
          Price Monitor
        </Text>
        <Pressable onPress={toggleTheme} style={styles.themeButton}>
          <MaterialCommunityIcons
            name={isDark ? 'weather-sunny' : 'weather-night'}
            size={24}
            color={colors.text}
          />
        </Pressable>
      </View>
      {isLoading ? (
        <View style={styles.loading}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : allProducts.length === 0 ? (
        <EmptyState
          icon="shopping-outline"
          title="Нет товаров"
          subtitle="Попробуйте выбрать другую категорию"
        />
      ) : (
        <FlatList
          data={feedItems}
          keyExtractor={item =>
            item.type === 'product' ? item.data.id : item.id
          }
          renderItem={renderItem}
          onEndReached={handleEndReached}
          onEndReachedThreshold={0.5}
          ListFooterComponent={renderFooter}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor={colors.primary}
            />
          }
          contentContainerStyle={styles.list}
        />
      )}
      <AdBanner />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    elevation: 2,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
  },
  themeButton: {
    padding: 8,
  },
  loading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  list: {
    paddingVertical: 8,
  },
  footer: {
    paddingVertical: 20,
    alignItems: 'center',
  },
  adDivider: {
    marginHorizontal: 16,
    marginVertical: 8,
    paddingVertical: 12,
    backgroundColor: '#F0F0F0',
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  adDividerText: {
    color: '#999999',
    fontSize: 12,
    fontWeight: '500',
  },
});

export default FeedScreen;
