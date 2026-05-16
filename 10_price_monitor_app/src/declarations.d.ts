declare module 'react-native-chart-kit' {
  import {ComponentType} from 'react';
  import {ViewStyle} from 'react-native';

  export interface ChartConfig {
    backgroundColor?: string;
    backgroundGradientFrom?: string;
    backgroundGradientTo?: string;
    decimalPlaces?: number;
    color?: (opacity: number) => string;
    labelColor?: (opacity: number) => string;
    style?: ViewStyle;
    propsForDots?: object;
  }

  export interface LineChartData {
    labels: string[];
    datasets: Array<{
      data: number[];
      color?: (opacity: number) => string;
      strokeWidth?: number;
    }>;
  }

  export interface LineChartProps {
    data: LineChartData;
    width: number;
    height: number;
    chartConfig: ChartConfig;
    bezier?: boolean;
    style?: ViewStyle;
    withDots?: boolean;
    withInnerLines?: boolean;
    withOuterLines?: boolean;
    withVerticalLabels?: boolean;
    withHorizontalLabels?: boolean;
  }

  export const LineChart: ComponentType<LineChartProps>;
}

declare module 'react-native-splash-screen' {
  const SplashScreen: {
    show(): void;
    hide(): void;
  };
  export default SplashScreen;
}

declare module '*.png' {
  const value: number;
  export default value;
}

declare module '*.jpg' {
  const value: number;
  export default value;
}
