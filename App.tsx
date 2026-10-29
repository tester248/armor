import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { PaperProvider } from 'react-native-paper';
import { StatusBar } from 'expo-status-bar';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useFonts } from 'expo-font';
import {
  IBMPlexSans_400Regular,
  IBMPlexSans_500Medium,
  IBMPlexSans_600SemiBold,
  IBMPlexSans_700Bold,
} from '@expo-google-fonts/ibm-plex-sans';
import {
  IBMPlexMono_400Regular,
  IBMPlexMono_500Medium,
  IBMPlexMono_600SemiBold,
} from '@expo-google-fonts/ibm-plex-mono';

import { armorTheme, FONT, navigationTheme, PALETTE, RADIUS } from './src/theme';
import DashboardScreen from './src/screens/DashboardScreen';
import InterlockScreen from './src/screens/InterlockScreen';
import VisionScreen from './src/screens/VisionScreen';
import IncidentsScreen from './src/screens/IncidentsScreen';
import SystemScreen from './src/screens/SystemScreen';

const Tab = createBottomTabNavigator();

const ICONS: Record<string, { on: keyof typeof MaterialCommunityIcons.glyphMap; off: keyof typeof MaterialCommunityIcons.glyphMap }> = {
  Live: { on: 'chart-line', off: 'chart-line-variant' },
  Safety: { on: 'shield-lock', off: 'shield-lock-outline' },
  Vision: { on: 'camera', off: 'camera-outline' },
  Records: { on: 'clipboard-alert', off: 'clipboard-alert-outline' },
  System: { on: 'cog', off: 'cog-outline' },
};

export default function App() {
  const [fontsLoaded, fontError] = useFonts({
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexSans_700Bold,
    IBMPlexMono_400Regular,
    IBMPlexMono_500Medium,
    IBMPlexMono_600SemiBold,
  });

  if (!fontsLoaded && !fontError) {
    return (
      <View style={styles.boot}>
        <ActivityIndicator color={PALETTE.primary} />
      </View>
    );
  }

  return (
    <PaperProvider theme={armorTheme}>
      <StatusBar style="light" />
      <NavigationContainer theme={navigationTheme}>
        <Tab.Navigator
          screenOptions={({ route }) => ({
            headerShown: false,
            tabBarActiveTintColor: PALETTE.primary,
            tabBarInactiveTintColor: PALETTE.textFaint,
            tabBarStyle: styles.tabBar,
            tabBarLabelStyle: styles.tabLabel,
            tabBarItemStyle: styles.tabItem,
            tabBarIcon: ({ focused }) => {
              const icon = ICONS[route.name] ?? { on: 'circle', off: 'circle-outline' };
              return (
                <View style={[styles.iconPill, focused && styles.iconPillActive]}>
                  <MaterialCommunityIcons
                    name={focused ? icon.on : icon.off}
                    size={21}
                    color={focused ? PALETTE.onPrimaryContainer : PALETTE.textFaint}
                  />
                </View>
              );
            },
          })}
        >
          <Tab.Screen name="Live" component={DashboardScreen} />
          <Tab.Screen name="Safety" component={InterlockScreen} />
          <Tab.Screen name="Vision" component={VisionScreen} />
          <Tab.Screen name="Records" component={IncidentsScreen} />
          <Tab.Screen name="System" component={SystemScreen} />
        </Tab.Navigator>
      </NavigationContainer>
    </PaperProvider>
  );
}

const styles = StyleSheet.create({
  boot: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: PALETTE.bg },
  tabBar: {
    backgroundColor: PALETTE.surface,
    borderTopColor: PALETTE.outlineSoft,
    borderTopWidth: 1,
    height: 70,
    paddingTop: 8,
    paddingBottom: 8,
    elevation: 0,
    shadowOpacity: 0,
  },
  tabItem: { paddingVertical: 0 },
  tabLabel: {
    fontFamily: FONT.sansMedium,
    fontSize: 10.5,
    letterSpacing: 0.2,
    marginTop: 2,
  },
  iconPill: {
    width: 46,
    height: 30,
    borderRadius: RADIUS.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconPillActive: { backgroundColor: PALETTE.primaryContainer },
});
