import React, {useCallback} from 'react';
import {
  View,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  StyleSheet,
  Text,
} from 'react-native';
import {useQuery} from '@tanstack/react-query';
import {useNavigation} from '@react-navigation/native';
import {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useTheme} from '../theme/ThemeContext';
import {useFavorites} from '../hooks/useFavorites';
import {getDealById} from '../api/services';
import {Product} from '../types';
import ProductCard from '../components/ProductCard';
import EmptyState from '../components/EmptyState';
import {RootStackParamList} from '../navigation/AppNavigator';

type FavNavProp = NativeStackNavigationProp<RootStackParamList>;

const FavoritesScreen: React.FC = () => {
  const {colors} = useTheme();
  const navigation = useNavigation<FavNavProp>();
  const {favoriteIds, loading: favLoading} = useFavorites();

  const {
    data: products,
    isLoading,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ['favorites', favoriteIds],
    queryFn: async () => {
      const results = await Promise.all(
        favoriteIds.map(id => getDealById(id)),
      );
      return results.filter((p): p is Product => p !== undefined);
    },
    enabled: !favLoading,
  });

  const renderItem = useCallback(
    ({item}: {item: Product}) => (
      <ProductCard
        product={item}
        onPress={() =>
          navigation.navigate('ProductDetail', {productId: item.id})
        }
      />
    ),
    [navigation],
  );

  if (isLoading || favLoading) {
    return (
      <View style={[styles.center, {backgroundColor: colors.background}]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={[styles.container, {backgroundColor: colors.background}]}>
      <Text style={[styles.header, {color: colors.text}]}>Избранное</Text>
      {!products || products.length === 0 ? (
        <EmptyState
          icon="heart-off-outline"
          title="Нет избранных товаров"
          subtitle="Добавляйте товары в избранное, чтобы следить за ценами"
        />
      ) : (
        <FlatList
          data={products}
          keyExtractor={item => item.id}
          renderItem={renderItem}
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
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    fontSize: 22,
    fontWeight: 'bold',
    padding: 16,
  },
  list: {
    paddingBottom: 16,
  },
});

export default FavoritesScreen;
