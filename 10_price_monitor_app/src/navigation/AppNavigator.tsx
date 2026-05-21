import React from 'react';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';

import FeedScreen from '../screens/FeedScreen';
import CategoriesScreen from '../screens/CategoriesScreen';
import AlertsScreen from '../screens/AlertsScreen';
import FavoritesScreen from '../screens/FavoritesScreen';
import ProfileScreen from '../screens/ProfileScreen';
import ProductDetailScreen from '../screens/ProductDetailScreen';
import SettingsScreen from '../screens/SettingsScreen';

export type RootStackParamList = {
  MainTabs: undefined;
  ProductDetail: {productId: string};
  Settings: undefined;
};

export type TabParamList = {
  Feed: {category?: string} | undefined;
  Categories: undefined;
  Alerts: undefined;
  Favorites: undefined;
  Profile: undefined;
};

const Tab = createBottomTabNavigator<TabParamList>();
const Stack = createNativeStackNavigator<RootStackParamList>();

const TabNavigator: React.FC = () => {
  const {colors} = useTheme();

  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: colors.border,
        },
        headerShown: false,
      }}>
      <Tab.Screen
        name="Feed"
        component={FeedScreen}
        options={{
          title: 'Скидки',
          tabBarIcon: ({color, size}) => (
            <MaterialCommunityIcons name="fire" color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="Categories"
        component={CategoriesScreen}
        options={{
          title: 'Категории',
          tabBarIcon: ({color, size}) => (
            <MaterialCommunityIcons name="shape" color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="Alerts"
        component={AlertsScreen}
        options={{
          title: 'Оповещения',
          tabBarIcon: ({color, size}) => (
            <MaterialCommunityIcons name="bell" color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="Favorites"
        component={FavoritesScreen}
        options={{
          title: 'Избранное',
          tabBarIcon: ({color, size}) => (
            <MaterialCommunityIcons name="heart" color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          title: 'Профиль',
          tabBarIcon: ({color, size}) => (
            <MaterialCommunityIcons name="account" color={color} size={size} />
          ),
        }}
      />
    </Tab.Navigator>
  );
};

const AppNavigator: React.FC = () => {
  return (
    <Stack.Navigator screenOptions={{headerShown: false}}>
      <Stack.Screen name="MainTabs" component={TabNavigator} />
      <Stack.Screen
        name="ProductDetail"
        component={ProductDetailScreen}
        options={{headerShown: true, title: 'Товар'}}
      />
      <Stack.Screen
        name="Settings"
        component={SettingsScreen}
        options={{headerShown: true, title: 'Настройки'}}
      />
    </Stack.Navigator>
  );
};

export default AppNavigator;
