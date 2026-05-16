import {useState, useEffect, useCallback} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const FAVORITES_KEY = '@price_monitor_favorites';

export const useFavorites = () => {
  const [favoriteIds, setFavoriteIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadFavorites();
  }, []);

  const loadFavorites = async () => {
    try {
      const stored = await AsyncStorage.getItem(FAVORITES_KEY);
      if (stored) {
        setFavoriteIds(JSON.parse(stored));
      }
    } catch (error) {
      console.error('Failed to load favorites:', error);
    } finally {
      setLoading(false);
    }
  };

  const addFavorite = useCallback(async (id: string) => {
    try {
      setFavoriteIds(prev => {
        const updated = [...prev, id];
        AsyncStorage.setItem(FAVORITES_KEY, JSON.stringify(updated));
        return updated;
      });
    } catch (error) {
      console.error('Failed to add favorite:', error);
    }
  }, []);

  const removeFavorite = useCallback(async (id: string) => {
    try {
      setFavoriteIds(prev => {
        const updated = prev.filter(fid => fid !== id);
        AsyncStorage.setItem(FAVORITES_KEY, JSON.stringify(updated));
        return updated;
      });
    } catch (error) {
      console.error('Failed to remove favorite:', error);
    }
  }, []);

  const isFavorite = useCallback(
    (id: string) => favoriteIds.includes(id),
    [favoriteIds],
  );

  const toggleFavorite = useCallback(
    async (id: string) => {
      if (isFavorite(id)) {
        await removeFavorite(id);
      } else {
        await addFavorite(id);
      }
    },
    [isFavorite, addFavorite, removeFavorite],
  );

  return {
    favoriteIds,
    loading,
    addFavorite,
    removeFavorite,
    isFavorite,
    toggleFavorite,
  };
};
