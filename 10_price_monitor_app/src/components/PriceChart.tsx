import React from 'react';
import {Dimensions, View} from 'react-native';
import {LineChart} from 'react-native-chart-kit';
import {useTheme} from '../theme/ThemeContext';
import {PricePoint} from '../types';

interface PriceChartProps {
  priceHistory: PricePoint[];
}

const PriceChart: React.FC<PriceChartProps> = ({priceHistory}) => {
  const {colors} = useTheme();
  const screenWidth = Dimensions.get('window').width - 32;

  if (priceHistory.length === 0) {
    return <View />;
  }

  const prices = priceHistory.map(p => p.price);
  const labels = priceHistory
    .filter((_, i) => i % 7 === 0)
    .map(p => {
      const parts = p.date.split('-');
      return `${parts[2]}.${parts[1]}`;
    });

  return (
    <LineChart
      data={{
        labels,
        datasets: [{data: prices, strokeWidth: 2}],
      }}
      width={screenWidth}
      height={200}
      chartConfig={{
        backgroundColor: colors.card,
        backgroundGradientFrom: colors.card,
        backgroundGradientTo: colors.card,
        decimalPlaces: 0,
        color: () => colors.primary,
        labelColor: () => colors.textSecondary,
        propsForDots: {r: '3'},
      }}
      bezier
      style={{borderRadius: 12}}
    />
  );
};

export default PriceChart;
