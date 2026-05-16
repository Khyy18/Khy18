import React from 'react';
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
import {RootStackParamList, TabParamList} from '../navigation/AppNavigator';

type FeedNavProp = NativeStackNavigationProp<RootStackParamList>;
type FeedRouteProp = RouteProp<TabParamList, 'Feed'>;

const FeedScreen: React.FC = () => {
  const {colors, toggleTheme, isDark} = useTheme();
  const navigation = useNavigation<FeedNavProp>();
  const route = useRoute<FeedRouteProp>();
  const category = (route.params as {category?: string} | undefined)?.category;

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

  const handleEndReached = () => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  };

  const renderItem = ({item}: {item: Product}) => (
    <ProductCard
      product={item}
      onPress={() =>
        navigation.navigate('ProductDetail', {productId: item.id})
      }
    />
  );

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
      ) : (
        <FlatList
          data={allProducts}
          keyExtractor={item => item.id}
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
});

export default FeedScreen;
