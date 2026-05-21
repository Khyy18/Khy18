import React from 'react';
import {View, FlatList, ActivityIndicator, StyleSheet, Text} from 'react-native';
import {useQuery} from '@tanstack/react-query';
import {useNavigation} from '@react-navigation/native';
import {NativeStackNavigationProp} from '@react-navigation/native-stack';
import {useTheme} from '../theme/ThemeContext';
import {getCategories} from '../api/services';
import {Category} from '../types';
import CategoryCard from '../components/CategoryCard';
import {RootStackParamList} from '../navigation/AppNavigator';

type CategoriesNavProp = NativeStackNavigationProp<RootStackParamList>;

const CategoriesScreen: React.FC = () => {
  const {colors} = useTheme();
  const navigation = useNavigation<CategoriesNavProp>();

  const {data: categories, isLoading} = useQuery({
    queryKey: ['categories'],
    queryFn: getCategories,
  });

  if (isLoading) {
    return (
      <View style={[styles.center, {backgroundColor: colors.background}]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const renderItem = ({item}: {item: Category}) => (
    <CategoryCard
      name={item.name}
      icon={item.icon}
      productCount={item.productCount}
      onPress={() => {
        navigation.navigate('MainTabs', {
          screen: 'Feed',
          params: {category: item.id},
        } as any);
      }}
    />
  );

  return (
    <View style={[styles.container, {backgroundColor: colors.background}]}>
      <Text style={[styles.header, {color: colors.text}]}>Категории</Text>
      <FlatList
        data={categories}
        keyExtractor={item => item.id}
        renderItem={renderItem}
        numColumns={2}
        contentContainerStyle={styles.list}
      />
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
    paddingHorizontal: 8,
    paddingBottom: 16,
  },
});

export default CategoriesScreen;
