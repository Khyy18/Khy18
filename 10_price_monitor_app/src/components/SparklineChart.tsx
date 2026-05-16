import React from 'react';
import {View} from 'react-native';
import {LineChart} from 'react-native-chart-kit';

interface SparklineChartProps {
  data: number[];
  width: number;
  height: number;
}

const SparklineChart: React.FC<SparklineChartProps> = ({
  data,
  width,
  height,
}) => {
  if (data.length < 2) {
    return <View style={{width, height}} />;
  }

  const isDown = data[data.length - 1] < data[0];
  const lineColor = isDown ? '#4CAF50' : '#F44336';

  return (
    <LineChart
      data={{
        labels: [],
        datasets: [{data, color: () => lineColor, strokeWidth: 2}],
      }}
      width={width}
      height={height}
      chartConfig={{
        backgroundColor: 'transparent',
        backgroundGradientFrom: 'transparent',
        backgroundGradientTo: 'transparent',
        color: () => lineColor,
        strokeWidth: 2,
        propsForDots: {r: '0'},
      }}
      bezier
      withDots={false}
      withInnerLines={false}
      withOuterLines={false}
      withVerticalLabels={false}
      withHorizontalLabels={false}
      style={{paddingRight: 0, paddingLeft: 0}}
    />
  );
};

export default SparklineChart;
