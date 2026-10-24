import React from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, {
  Defs,
  LinearGradient,
  RadialGradient,
  Stop,
  Polygon,
  Path,
  G,
  Circle
} from 'react-native-svg';

interface LDEmblemProps {
  size?: number;
}

export const LDEmblem: React.FC<LDEmblemProps> = ({ size = 36 }) => {
  return (
    <View style={{ width: size, height: size }}>
      <Svg viewBox="0 0 100 100" width={size} height={size}>
        <Defs>
          {/* Main 3D Metallic Gold Gradient */}
          <LinearGradient id="ldGold" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#FFF1D0" />
            <Stop offset="25%" stopColor="#E2BD6D" />
            <Stop offset="55%" stopColor="#C5A059" />
            <Stop offset="85%" stopColor="#8C6A28" />
            <Stop offset="100%" stopColor="#F5D78E" />
          </LinearGradient>

          {/* Dark Facet Shadow */}
          <LinearGradient id="ldDarkFacet" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#2A2215" />
            <Stop offset="100%" stopColor="#14110B" />
          </LinearGradient>

          {/* Core Radial Glow */}
          <RadialGradient id="ldGlow" cx="50%" cy="50%" r="50%">
            <Stop offset="0%" stopColor="#C5A059" stopOpacity={0.25} />
            <Stop offset="100%" stopColor="#C5A059" stopOpacity={0} />
          </RadialGradient>
        </Defs>

        {/* Ambient Glow */}
        <Circle cx="50" cy="50" r="48" fill="url(#ldGlow)" />

        {/* Outer Faceted 3D Hexagon */}
        <Polygon
          points="50,4 90,26 90,74 50,96 10,74 10,26"
          fill="url(#ldDarkFacet)"
          stroke="url(#ldGold)"
          strokeWidth="2.5"
        />

        {/* Inner Precision Hexagon Ring */}
        <Polygon
          points="50,11 83,30 83,70 50,89 17,70 17,30"
          fill="none"
          stroke="url(#ldGold)"
          strokeWidth="1.2"
          strokeOpacity={0.5}
        />

        {/* 3D Monogram "L" & "D" Stylized Institutional Cuts */}
        <G fill="url(#ldGold)">
          {/* Letter L - Angular Institutional Cut */}
          <Path d="M30 30 L37 30 L37 63 L52 63 L52 70 L30 70 Z" />
          {/* Letter D - Precision Diamond Arch */}
          <Path d="M47 30 L62 30 C71 30, 77 36, 77 50 C77 64, 71 70, 62 70 L47 70 Z M54 37 L54 63 L61 63 C66 63, 70 59, 70 50 C70 41, 66 37, 61 37 Z" />
        </G>
      </Svg>
    </View>
  );
};
