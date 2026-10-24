import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import * as Haptics from 'expo-haptics';
import { Radar, CandlestickChart, Newspaper, BookMarked, Calculator } from 'lucide-react-native';
import { SignalsScreen } from '../screens/SignalsScreen';
import { ChartScreen } from '../screens/ChartScreen';
import { NewsScreen } from '../screens/NewsScreen';
import { JournalScreen } from '../screens/JournalScreen';
import { RiskCalculatorScreen } from '../screens/RiskCalculatorScreen';

const Tab = createBottomTabNavigator();

export const RootNavigator: React.FC = () => {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: '#121212',
          borderTopColor: '#242424',
          borderTopWidth: 1,
          height: 64,
          paddingBottom: 8,
          paddingTop: 8
        },
        tabBarActiveTintColor: '#C5A059',
        tabBarInactiveTintColor: '#666666',
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: '700'
        }
      }}
      screenListeners={{
        tabPress: () => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        }
      }}
    >
      <Tab.Screen
        name="Signals"
        component={SignalsScreen}
        options={{
          tabBarLabel: 'الصفقات SMC',
          tabBarIcon: ({ color, size }) => <Radar size={size} color={color} />
        }}
      />
      <Tab.Screen
        name="Chart"
        component={ChartScreen}
        options={{
          tabBarLabel: 'الشارت الحي',
          tabBarIcon: ({ color, size }) => <CandlestickChart size={size} color={color} />
        }}
      />
      <Tab.Screen
        name="News"
        component={NewsScreen}
        options={{
          tabBarLabel: 'الأخبار المباشرة',
          tabBarIcon: ({ color, size }) => <Newspaper size={size} color={color} />
        }}
      />
      <Tab.Screen
        name="Journal"
        component={JournalScreen}
        options={{
          tabBarLabel: 'المذكرة Journal',
          tabBarIcon: ({ color, size }) => <BookMarked size={size} color={color} />
        }}
      />
      <Tab.Screen
        name="Risk"
        component={RiskCalculatorScreen}
        options={{
          tabBarLabel: 'إدارة 1% Risk',
          tabBarIcon: ({ color, size }) => <Calculator size={size} color={color} />
        }}
      />
    </Tab.Navigator>
  );
};
