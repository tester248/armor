import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { PaperProvider } from 'react-native-paper';
import { armorTheme } from './src/theme';
import DashboardScreen from './src/screens/DashboardScreen';
import InterlockScreen from './src/screens/InterlockScreen';
import IncidentsScreen from './src/screens/IncidentsScreen';
import WorkersScreen from './src/screens/WorkersScreen';

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <PaperProvider theme={armorTheme}>
      <NavigationContainer>
        <Tab.Navigator
          screenOptions={{
            headerStyle: { backgroundColor: '#0b0f19' },
            headerTintColor: '#f8fafc',
            tabBarStyle: { backgroundColor: '#121a2b' },
            tabBarActiveTintColor: '#06b6d4',
            tabBarInactiveTintColor: '#94a3b8',
          }}
        >
          <Tab.Screen name="Live" component={DashboardScreen} options={{ tabBarIcon: ({ color }) => <TabIcon name="chart-line" color={color} /> }} />
          <Tab.Screen name="Safety" component={InterlockScreen} options={{ tabBarIcon: ({ color }) => <TabIcon name="lock" color={color} /> }} />
          <Tab.Screen name="Incidents" component={IncidentsScreen} options={{ tabBarIcon: ({ color }) => <TabIcon name="clipboard-alert" color={color} /> }} />
          <Tab.Screen name="Badges" component={WorkersScreen} options={{ tabBarIcon: ({ color }) => <TabIcon name="badge-account" color={color} /> }} />
        </Tab.Navigator>
      </NavigationContainer>
    </PaperProvider>
  );
}

import { View } from 'react-native';
import { Icon } from 'react-native-paper';
function TabIcon({ name, color }: { name: string; color: string }) {
  return <View><Icon source={name} size={22} color={color} /></View>;
}