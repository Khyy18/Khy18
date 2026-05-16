export interface ThemeColors {
  primary: string;
  background: string;
  card: string;
  text: string;
  textSecondary: string;
  border: string;
  success: string;
  error: string;
  warning: string;
}

export const lightTheme: ThemeColors = {
  primary: '#FF6B35',
  background: '#FFFFFF',
  card: '#F8F8F8',
  text: '#1A1A2E',
  textSecondary: '#666666',
  border: '#E0E0E0',
  success: '#4CAF50',
  error: '#F44336',
  warning: '#FF9800',
};

export const darkTheme: ThemeColors = {
  primary: '#FF6B35',
  background: '#1A1A2E',
  card: '#2D2D44',
  text: '#FFFFFF',
  textSecondary: '#AAAAAA',
  border: '#3D3D5C',
  success: '#66BB6A',
  error: '#EF5350',
  warning: '#FFA726',
};
