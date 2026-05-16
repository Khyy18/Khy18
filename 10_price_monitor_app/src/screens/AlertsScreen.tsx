import React, {useState} from 'react';
import {
  View,
  FlatList,
  Text,
  TextInput,
  Pressable,
  Modal,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import {useQuery, useMutation, useQueryClient} from '@tanstack/react-query';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import {useTheme} from '../theme/ThemeContext';
import {getAlerts, createAlert} from '../api/services';
import {Alert as AlertType} from '../types';
import AlertItem from '../components/AlertItem';
import EmptyState from '../components/EmptyState';

const AlertsScreen: React.FC = () => {
  const {colors} = useTheme();
  const queryClient = useQueryClient();
  const [modalVisible, setModalVisible] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [maxPrice, setMaxPrice] = useState('');

  const {data: alerts, isLoading} = useQuery({
    queryKey: ['alerts'],
    queryFn: getAlerts,
  });

  const createMutation = useMutation({
    mutationFn: createAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({queryKey: ['alerts']});
      setModalVisible(false);
      setKeyword('');
      setMaxPrice('');
    },
  });

  const handleCreate = () => {
    if (!keyword.trim() || !maxPrice.trim()) {
      return;
    }
    createMutation.mutate({
      keyword: keyword.trim(),
      maxPrice: Number(maxPrice),
      category: 'all',
      active: true,
    });
  };

  const handleToggle = (_id: string, _active: boolean) => {
    // In a real app, would call API to toggle
  };

  if (isLoading) {
    return (
      <View style={[styles.center, {backgroundColor: colors.background}]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={[styles.container, {backgroundColor: colors.background}]}>
      <View style={styles.headerRow}>
        <Text style={[styles.headerTitle, {color: colors.text}]}>
          Оповещения
        </Text>
        <Pressable
          onPress={() => setModalVisible(true)}
          style={[styles.addButton, {backgroundColor: colors.primary}]}>
          <MaterialCommunityIcons name="plus" size={24} color="#FFFFFF" />
        </Pressable>
      </View>

      {!alerts || alerts.length === 0 ? (
        <EmptyState
          icon="bell-off-outline"
          title="Нет оповещений"
          subtitle="Создайте алерт, чтобы получать уведомления о снижении цен"
        />
      ) : (
        <FlatList
          data={alerts}
          keyExtractor={item => item.id}
          renderItem={({item}: {item: AlertType}) => (
            <AlertItem alert={item} onToggle={handleToggle} />
          )}
          contentContainerStyle={styles.list}
        />
      )}

      <Modal
        visible={modalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => setModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, {backgroundColor: colors.card}]}>
            <Text style={[styles.modalTitle, {color: colors.text}]}>
              Новый алерт
            </Text>
            <TextInput
              value={keyword}
              onChangeText={setKeyword}
              placeholder="Ключевое слово"
              placeholderTextColor={colors.textSecondary}
              style={[
                styles.input,
                {
                  backgroundColor: colors.background,
                  color: colors.text,
                  borderColor: colors.border,
                },
              ]}
            />
            <TextInput
              value={maxPrice}
              onChangeText={setMaxPrice}
              placeholder="Максимальная цена"
              placeholderTextColor={colors.textSecondary}
              keyboardType="numeric"
              style={[
                styles.input,
                {
                  backgroundColor: colors.background,
                  color: colors.text,
                  borderColor: colors.border,
                },
              ]}
            />
            <Pressable
              onPress={handleCreate}
              style={[styles.submitButton, {backgroundColor: colors.primary}]}>
              <Text style={styles.submitButtonText}>Создать алерт</Text>
            </Pressable>
            <Pressable
              onPress={() => setModalVisible(false)}
              style={styles.cancelButton}>
              <Text style={[styles.cancelText, {color: colors.textSecondary}]}>
                Отмена
              </Text>
            </Pressable>
          </View>
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
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: 'bold',
  },
  addButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
  },
  list: {
    paddingBottom: 16,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    padding: 24,
  },
  modalContent: {
    borderRadius: 16,
    padding: 24,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 16,
  },
  input: {
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    marginBottom: 12,
  },
  submitButton: {
    alignItems: 'center',
    paddingVertical: 14,
    borderRadius: 12,
    marginTop: 8,
  },
  submitButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
  },
  cancelButton: {
    alignItems: 'center',
    paddingVertical: 12,
    marginTop: 8,
  },
  cancelText: {
    fontSize: 14,
  },
});

export default AlertsScreen;
