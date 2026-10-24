import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Dimensions,
  ActivityIndicator
} from 'react-native';
import Svg, { Rect, Line, Text as SvgText } from 'react-native-svg';
import * as Haptics from 'expo-haptics';
import { INITIAL_MOBILE_ASSETS, fetchLiveCandlesDirect, Candle, LiveMarketAsset } from '../services/liveMarketClient';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CHART_WIDTH = SCREEN_WIDTH - 32;
const CHART_HEIGHT = 280;

export const ChartScreen: React.FC = () => {
  const [selectedAsset, setSelectedAsset] = useState<LiveMarketAsset>(INITIAL_MOBILE_ASSETS[0]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [interval, setIntervalTimeframe] = useState<'5m' | '15m' | '1h' | '4h'>('15m');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    async function load() {
      setLoading(true);
      const data = await fetchLiveCandlesDirect(selectedAsset.symbol, interval);
      if (isMounted) {
        setCandles(data);
        setLoading(false);
      }
    }
    load();
    const timer = setInterval(load, 20000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, [selectedAsset, interval]);

  const selectAsset = async (asset: LiveMarketAsset) => {
    await Haptics.selectionAsync();
    setSelectedAsset(asset);
  };

  const selectTimeframe = async (tf: '5m' | '15m' | '1h' | '4h') => {
    await Haptics.selectionAsync();
    setIntervalTimeframe(tf);
  };

  // SVG Chart Scaling
  const displayCandles = candles.slice(-28);
  const minPrice = displayCandles.length ? Math.min(...displayCandles.map(c => c.low)) : 0;
  const maxPrice = displayCandles.length ? Math.max(...displayCandles.map(c => c.high)) : 1;
  const priceRange = maxPrice - minPrice || 1;

  const candleWidth = (CHART_WIDTH - 40) / (displayCandles.length || 1);

  return (
    <View style={styles.container}>
      {/* Asset Switcher Pills */}
      <View style={styles.topSelector}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.assetScroll}>
          {INITIAL_MOBILE_ASSETS.map((asset) => {
            const isSelected = asset.symbol === selectedAsset.symbol;
            return (
              <TouchableOpacity
                key={asset.symbol}
                style={[styles.assetPill, isSelected && styles.assetPillActive]}
                onPress={() => selectAsset(asset)}
              >
                <Text style={[styles.assetPillText, isSelected && styles.assetPillTextActive]}>
                  {asset.symbol}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Price Summary Header */}
      <View style={styles.priceHeader}>
        <View>
          <Text style={styles.symbolTitle}>{selectedAsset.nameAr || selectedAsset.name}</Text>
          <Text style={styles.livePriceText}>
            {selectedAsset.price.toFixed(selectedAsset.decimals)}{' '}
            <Text style={selectedAsset.change24h >= 0 ? styles.posText : styles.negText}>
              {selectedAsset.change24h >= 0 ? '+' : ''}{selectedAsset.change24h}%
            </Text>
          </Text>
        </View>

        {/* Timeframe Selector */}
        <View style={styles.tfContainer}>
          {(['5m', '15m', '1h', '4h'] as const).map((tf) => (
            <TouchableOpacity
              key={tf}
              style={[styles.tfBtn, interval === tf && styles.tfBtnActive]}
              onPress={() => selectTimeframe(tf)}
            >
              <Text style={[styles.tfText, interval === tf && styles.tfTextActive]}>
                {tf.toUpperCase()}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Candlestick Chart Area */}
      <View style={styles.chartCard}>
        {loading ? (
          <View style={styles.loadingBox}>
            <ActivityIndicator size="large" color="#C5A059" />
            <Text style={styles.chartLoadingText}>جاري جلب شموع التداول الحية...</Text>
          </View>
        ) : (
          <Svg width={CHART_WIDTH} height={CHART_HEIGHT}>
            {/* Price Grid Lines */}
            {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
              const y = 20 + (CHART_HEIGHT - 50) * ratio;
              const price = maxPrice - priceRange * ratio;
              return (
                <React.Fragment key={ratio}>
                  <Line
                    x1={0}
                    y1={y}
                    x2={CHART_WIDTH - 45}
                    y2={y}
                    stroke="#262626"
                    strokeWidth={0.8}
                    strokeDasharray="4,4"
                  />
                  <SvgText
                    x={CHART_WIDTH - 40}
                    y={y + 4}
                    fill="#666"
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    {price.toFixed(selectedAsset.decimals > 2 ? 4 : 1)}
                  </SvgText>
                </React.Fragment>
              );
            })}

            {/* Candlesticks */}
            {displayCandles.map((c, idx) => {
              const isUp = c.close >= c.open;
              const color = isUp ? '#10B981' : '#EF4444';
              const x = 10 + idx * candleWidth;
              const yHigh = 20 + ((maxPrice - c.high) / priceRange) * (CHART_HEIGHT - 50);
              const yLow = 20 + ((maxPrice - c.low) / priceRange) * (CHART_HEIGHT - 50);
              const yOpen = 20 + ((maxPrice - c.open) / priceRange) * (CHART_HEIGHT - 50);
              const yClose = 20 + ((maxPrice - c.close) / priceRange) * (CHART_HEIGHT - 50);

              const bodyY = Math.min(yOpen, yClose);
              const bodyHeight = Math.max(2, Math.abs(yClose - yOpen));

              return (
                <React.Fragment key={idx}>
                  {/* High/Low Wick */}
                  <Line
                    x1={x + candleWidth * 0.4}
                    y1={yHigh}
                    x2={x + candleWidth * 0.4}
                    y2={yLow}
                    stroke={color}
                    strokeWidth={1.2}
                  />
                  {/* Candle Body */}
                  <Rect
                    x={x}
                    y={bodyY}
                    width={Math.max(2, candleWidth * 0.8)}
                    height={bodyHeight}
                    fill={color}
                    rx={1}
                  />
                </React.Fragment>
              );
            })}
          </Svg>
        )}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#121212', paddingTop: 50, paddingHorizontal: 16 },
  topSelector: { marginBottom: 16 },
  assetScroll: { gap: 8 },
  assetPill: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: '#1E1E1E',
    borderWidth: 1,
    borderColor: '#2A2A2A'
  },
  assetPillActive: { backgroundColor: '#C5A059', borderColor: '#C5A059' },
  assetPillText: { color: '#999', fontSize: 12, fontWeight: '700' },
  assetPillTextActive: { color: '#121212', fontWeight: '900' },
  priceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16
  },
  symbolTitle: { color: '#999', fontSize: 12, fontWeight: '600' },
  livePriceText: { color: '#FFF', fontSize: 22, fontWeight: '900', marginTop: 2 },
  posText: { color: '#10B981', fontSize: 13 },
  negText: { color: '#EF4444', fontSize: 13 },
  tfContainer: {
    flexDirection: 'row',
    backgroundColor: '#1E1E1E',
    borderRadius: 10,
    padding: 3,
    borderWidth: 1,
    borderColor: '#282828'
  },
  tfBtn: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6 },
  tfBtnActive: { backgroundColor: '#C5A059' },
  tfText: { color: '#777', fontSize: 10, fontWeight: '800' },
  tfTextActive: { color: '#121212' },
  chartCard: {
    backgroundColor: '#181818',
    borderRadius: 16,
    padding: 10,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: CHART_HEIGHT
  },
  loadingBox: { padding: 40, alignItems: 'center' },
  chartLoadingText: { color: '#888', marginTop: 10, fontSize: 11 }
});
