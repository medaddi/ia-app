import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  StyleSheet,
  ActivityIndicator
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { 
  Radio, 
  AlertOctagon, 
  ArrowUpRight, 
  ArrowDownRight, 
  ShieldCheck, 
  Target, 
  Lock, 
  BookMarked,
  Award
} from 'lucide-react-native';
import { LDEmblem } from '../components/LDEmblem';
import { INITIAL_MOBILE_ASSETS, fetchLiveCandlesDirect, LiveMarketAsset } from '../services/liveMarketClient';
import { fetchLiveNewsDirect, MobileNewsItem } from '../services/liveNewsClient';
import { evaluateMobileSignal, MobileSignal } from '../services/smcDecisionEngine';
import { loadUserSettings, saveJournalEntry, UserSettings } from '../services/localDatabase';

export const SignalsScreen: React.FC = () => {
  const [signals, setSignals] = useState<MobileSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const userSets = await loadUserSettings();
      setSettings(userSets);

      const news = await fetchLiveNewsDirect();
      const calculatedSignals: MobileSignal[] = [];

      for (const asset of INITIAL_MOBILE_ASSETS) {
        const candles = await fetchLiveCandlesDirect(asset.symbol, '15m');
        const sig = evaluateMobileSignal(
          asset,
          candles,
          news,
          userSets.accountBalance,
          userSets.riskPerTrade
        );
        calculatedSignals.push(sig);
      }

      setSignals(calculatedSignals);
    } catch (e) {
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    await loadData();
  };

  const handleSaveToJournal = async (sig: MobileSignal) => {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    await saveJournalEntry({
      id: `jnl-${Date.now()}`,
      symbol: sig.symbol,
      direction: sig.signalType === 'BUY' ? 'BUY' : 'SELL',
      entryPrice: sig.entryPrice,
      stopLoss: sig.stopLoss,
      takeProfit1: sig.target1,
      takeProfit2: sig.target2,
      lotSize: sig.recommendedLot,
      riskAmountUsd: sig.riskAmountUsd,
      status: 'PENDING',
      pnlUsd: 0.0,
      setupStrategy: sig.strategyUsed,
      notes: sig.reasonsAr[0] || 'تم حفظ الصفقة آلياً من محرك القرارات',
      createdAt: new Date().toISOString()
    });
    setSavedId(sig.id);
    setTimeout(() => setSavedId(null), 2500);
  };

  return (
    <View style={styles.container}>
      {/* Header Bar */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <LDEmblem size={34} />
          <View>
            <Text style={styles.brandTitle}>LIQUIDITY DISSECTION</Text>
            <Text style={styles.brandSubtitle}>PRIVATE DESK • 10-PILLAR SMC ENGINE</Text>
          </View>
        </View>
        <View style={styles.liveBadge}>
          <View style={styles.liveDot} />
          <Text style={styles.liveText}>STANDALONE</Text>
        </View>
      </View>

      <ScrollView
        style={styles.scroll}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#C5A059" />
        }
      >
        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color="#C5A059" />
            <Text style={styles.loadingText}>جاري فحص السيولة وتأكيد الشموع...</Text>
          </View>
        ) : (
          signals.map((sig) => {
            const isBuy = sig.signalType === 'BUY';
            const isLockout = sig.newsLockoutActive;

            return (
              <View
                key={sig.id}
                style={[
                  styles.card,
                  isLockout && styles.cardLockout
                ]}
              >
                {/* Top Row: Symbol & Status Badge */}
                <View style={styles.cardHeader}>
                  <View>
                    <Text style={styles.symbolText}>{sig.symbol}</Text>
                    <Text style={styles.assetNameText}>{sig.assetName}</Text>
                  </View>

                  {isLockout ? (
                    <View style={styles.lockoutBadge}>
                      <AlertOctagon size={13} color="#F87171" />
                      <Text style={styles.lockoutText}>⛔ NEWS LOCKOUT</Text>
                    </View>
                  ) : sig.decisionStatus === 'ALLOWED' ? (
                    <View style={[styles.decisionBadge, isBuy ? styles.buyBadge : styles.sellBadge]}>
                      {isBuy ? <ArrowUpRight size={13} color="#FFF" /> : <ArrowDownRight size={13} color="#FFF" />}
                      <Text style={styles.decisionBadgeText}>{sig.signalType} A+ SETUP</Text>
                    </View>
                  ) : (
                    <View style={styles.waitBadge}>
                      <Text style={styles.waitBadgeText}>⏳ في انتظار التأكيد</Text>
                    </View>
                  )}
                </View>

                {/* Macro Confluence Banner */}
                {sig.newsConfluenceAr && (
                  <View style={[styles.newsStrip, isLockout && styles.newsStripLockout]}>
                    <Radio size={12} color={isLockout ? '#F87171' : '#C5A059'} />
                    <Text style={styles.newsStripText} numberOfLines={2}>
                      {sig.newsConfluenceAr}
                    </Text>
                  </View>
                )}

                {/* Score & Risk/Reward */}
                <View style={styles.scoreRow}>
                  <View style={styles.scoreItem}>
                    <Award size={14} color="#C5A059" />
                    <Text style={styles.scoreLabel}>Score:</Text>
                    <Text style={styles.scoreValue}>{sig.tradeScore}/100</Text>
                  </View>
                  <View style={styles.scoreItem}>
                    <Target size={14} color="#C5A059" />
                    <Text style={styles.scoreLabel}>R:R:</Text>
                    <Text style={styles.scoreValue}>{sig.riskReward}</Text>
                  </View>
                  <View style={styles.scoreItem}>
                    <ShieldCheck size={14} color="#34D399" />
                    <Text style={styles.scoreLabel}>Risk 1%:</Text>
                    <Text style={styles.scoreValue}>${sig.riskAmountUsd.toFixed(0)}</Text>
                  </View>
                </View>

                {/* Numerical Execution Levels */}
                <View style={styles.levelsGrid}>
                  <View style={styles.levelBox}>
                    <Text style={styles.levelLabel}>سعر الدخول (Entry)</Text>
                    <Text style={styles.levelValue}>{sig.entryPrice}</Text>
                  </View>
                  <View style={[styles.levelBox, styles.slBox]}>
                    <Text style={styles.levelLabel}>الستوب (4H SL)</Text>
                    <Text style={[styles.levelValue, styles.slValue]}>{sig.stopLoss}</Text>
                  </View>
                  <View style={[styles.levelBox, styles.tpBox]}>
                    <Text style={styles.levelLabel}>الهدف الأول (TP1)</Text>
                    <Text style={[styles.levelValue, styles.tpValue]}>{sig.target1}</Text>
                  </View>
                  <View style={[styles.levelBox, styles.tpBox]}>
                    <Text style={styles.levelLabel}>الهدف الثاني (TP2)</Text>
                    <Text style={[styles.levelValue, styles.tpValue]}>{sig.target2}</Text>
                  </View>
                </View>

                {/* Action Buttons */}
                <View style={styles.cardActions}>
                  <Text style={styles.lotText}>
                    حجم اللوت المقترح: <Text style={styles.lotHighlight}>{sig.recommendedLot} Lot</Text>
                  </Text>
                  <TouchableOpacity
                    style={styles.journalBtn}
                    onPress={() => handleSaveToJournal(sig)}
                  >
                    <BookMarked size={14} color="#C5A059" />
                    <Text style={styles.journalBtnText}>
                      {savedId === sig.id ? 'تم الحفظ في المذكرة ✓' : 'حفظ في Journal'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#121212' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 54,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#242424',
    backgroundColor: '#161616'
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  brandTitle: { color: '#FFF', fontSize: 13, fontWeight: '900', letterSpacing: 1 },
  brandSubtitle: { color: '#C5A059', fontSize: 9, fontWeight: '700', marginTop: 1 },
  liveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(197, 160, 89, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(197, 160, 89, 0.3)'
  },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#C5A059' },
  liveText: { color: '#C5A059', fontSize: 9, fontWeight: '800' },
  scroll: { flex: 1, padding: 14 },
  centerContainer: { padding: 40, alignItems: 'center' },
  loadingText: { color: '#888', marginTop: 12, fontSize: 12 },
  card: {
    backgroundColor: '#1A1A1A',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    padding: 16,
    marginBottom: 14
  },
  cardLockout: { borderColor: 'rgba(248, 113, 113, 0.4)' },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  symbolText: { color: '#FFF', fontSize: 16, fontWeight: '900' },
  assetNameText: { color: '#999', fontSize: 11, marginTop: 2 },
  lockoutBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(248, 113, 113, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(248, 113, 113, 0.3)'
  },
  lockoutText: { color: '#F87171', fontSize: 10, fontWeight: '900' },
  decisionBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8
  },
  buyBadge: { backgroundColor: '#059669' },
  sellBadge: { backgroundColor: '#DC2626' },
  decisionBadgeText: { color: '#FFF', fontSize: 11, fontWeight: '900' },
  waitBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.3)'
  },
  waitBadgeText: { color: '#FBBF24', fontSize: 10, fontWeight: '800' },
  newsStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#141414',
    padding: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#282828',
    marginBottom: 12
  },
  newsStripLockout: { backgroundColor: 'rgba(248, 113, 113, 0.08)', borderColor: 'rgba(248, 113, 113, 0.25)' },
  newsStripText: { color: '#CCC', fontSize: 11, flex: 1, lineHeight: 15 },
  scoreRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#141414',
    padding: 10,
    borderRadius: 10,
    marginBottom: 12
  },
  scoreItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  scoreLabel: { color: '#777', fontSize: 11 },
  scoreValue: { color: '#FFF', fontSize: 12, fontWeight: '800' },
  levelsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  levelBox: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#141414',
    padding: 10,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#262626'
  },
  slBox: { borderColor: 'rgba(248, 113, 113, 0.3)' },
  tpBox: { borderColor: 'rgba(52, 211, 153, 0.3)' },
  levelLabel: { color: '#777', fontSize: 10, marginBottom: 4 },
  levelValue: { color: '#FFF', fontSize: 13, fontWeight: '800' },
  slValue: { color: '#F87171' },
  tpValue: { color: '#34D399' },
  cardActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#242424'
  },
  lotText: { color: '#888', fontSize: 11 },
  lotHighlight: { color: '#C5A059', fontWeight: '800' },
  journalBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(197, 160, 89, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(197, 160, 89, 0.3)',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8
  },
  journalBtnText: { color: '#C5A059', fontSize: 10, fontWeight: '800' }
});
