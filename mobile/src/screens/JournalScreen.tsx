import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { BookMarked, CheckCircle2, XCircle, Clock } from 'lucide-react-native';
import { loadJournalEntries, saveJournalEntry, JournalEntry } from '../services/localDatabase';

export const JournalScreen: React.FC = () => {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadEntries();
  }, []);

  const loadEntries = async () => {
    setLoading(true);
    const data = await loadJournalEntries();
    setEntries(data);
    setLoading(false);
  };

  const updateOutcome = async (entry: JournalEntry, outcome: 'TP1_HIT' | 'TP2_HIT' | 'SL_HIT') => {
    await Haptics.notificationAsync(
      outcome === 'SL_HIT'
        ? Haptics.NotificationFeedbackType.Warning
        : Haptics.NotificationFeedbackType.Success
    );
    const pnl = outcome === 'SL_HIT' ? -entry.riskAmountUsd : entry.riskAmountUsd * (outcome === 'TP1_HIT' ? 1.8 : 3.2);
    const updated: JournalEntry = {
      ...entry,
      status: outcome,
      pnlUsd: pnl
    };
    await saveJournalEntry(updated);
    await loadEntries();
  };

  const totalPnl = entries.reduce((sum, e) => sum + (e.pnlUsd || 0), 0);
  const closedCount = entries.filter(e => e.status !== 'PENDING').length;
  const winCount = entries.filter(e => e.status === 'TP1_HIT' || e.status === 'TP2_HIT').length;
  const winRate = closedCount > 0 ? Math.round((winCount / closedCount) * 100) : 100;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <BookMarked size={20} color="#C5A059" />
          <Text style={styles.headerTitle}>مذكرة الصفقات والمحفظة المحلية (SQLite)</Text>
        </View>
      </View>

      <ScrollView style={styles.scroll}>
        {/* Metric Cards */}
        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>إجمالي الأرباح PnL</Text>
            <Text style={[styles.statValue, totalPnl >= 0 ? styles.posText : styles.negText]}>
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(1)}
            </Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>نسبة الصفقات الرابحة</Text>
            <Text style={[styles.statValue, styles.goldText]}>{winRate}%</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>الصفقات المسجلة</Text>
            <Text style={styles.statValue}>{entries.length}</Text>
          </View>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color="#C5A059" style={{ marginTop: 40 }} />
        ) : entries.length === 0 ? (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyTitle}>المذكرة فارغة حالياً</Text>
            <Text style={styles.emptyDesc}>
              عند ظهور إشارة A+ في شاشة الصفقات، اضغط على زر "حفظ في Journal" لحفظها مباشرة في قاعدة البيانات المحلية بهاتفك.
            </Text>
          </View>
        ) : (
          entries.map((entry) => {
            const isBuy = entry.direction === 'BUY';
            const isClosed = entry.status !== 'PENDING';

            return (
              <View key={entry.id} style={styles.entryCard}>
                <View style={styles.entryHeader}>
                  <View style={styles.entryTitleRow}>
                    <Text style={styles.symbolText}>{entry.symbol}</Text>
                    <Text style={[styles.dirBadge, isBuy ? styles.buyText : styles.sellText]}>
                      {entry.direction} ({entry.lotSize}L)
                    </Text>
                  </View>
                  <Text style={[styles.statusBadge, isClosed ? (entry.pnlUsd >= 0 ? styles.tpStatus : styles.slStatus) : styles.pendingStatus]}>
                    {entry.status}
                  </Text>
                </View>

                <View style={styles.levelsRow}>
                  <Text style={styles.levelText}>دخول: <Text style={styles.boldWhite}>{entry.entryPrice}</Text></Text>
                  <Text style={styles.levelText}>ستوب: <Text style={styles.boldRed}>{entry.stopLoss}</Text></Text>
                  <Text style={styles.levelText}>هدف: <Text style={styles.boldGreen}>{entry.takeProfit1}</Text></Text>
                </View>

                {entry.notes && (
                  <Text style={styles.noteText}>{entry.notes}</Text>
                )}

                {/* Outcome Setter Buttons if still Pending */}
                {!isClosed && (
                  <View style={styles.outcomeRow}>
                    <TouchableOpacity
                      style={[styles.outcomeBtn, styles.tpBtn]}
                      onPress={() => updateOutcome(entry, 'TP1_HIT')}
                    >
                      <CheckCircle2 size={12} color="#FFF" />
                      <Text style={styles.outcomeBtnText}>ضرب TP1 (+1:2)</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.outcomeBtn, styles.tpBtn]}
                      onPress={() => updateOutcome(entry, 'TP2_HIT')}
                    >
                      <CheckCircle2 size={12} color="#FFF" />
                      <Text style={styles.outcomeBtnText}>ضرب TP2 (+1:3.5)</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.outcomeBtn, styles.slBtn]}
                      onPress={() => updateOutcome(entry, 'SL_HIT')}
                    >
                      <XCircle size={12} color="#FFF" />
                      <Text style={styles.outcomeBtnText}>ضرب SL (-1%)</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            );
          })
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#121212', paddingTop: 50 },
  header: {
    paddingHorizontal: 16,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#242424'
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { color: '#FFF', fontSize: 13, fontWeight: '800' },
  scroll: { flex: 1, padding: 14 },
  statsRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  statCard: {
    flex: 1,
    backgroundColor: '#181818',
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)'
  },
  statLabel: { color: '#777', fontSize: 10, marginBottom: 4 },
  statValue: { color: '#FFF', fontSize: 15, fontWeight: '900' },
  posText: { color: '#10B981' },
  negText: { color: '#EF4444' },
  goldText: { color: '#C5A059' },
  emptyBox: { padding: 40, alignItems: 'center' },
  emptyTitle: { color: '#FFF', fontSize: 14, fontWeight: '800', marginBottom: 8 },
  emptyDesc: { color: '#888', fontSize: 12, textAlign: 'center', lineHeight: 18 },
  entryCard: {
    backgroundColor: '#181818',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    marginBottom: 10
  },
  entryHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  entryTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  symbolText: { color: '#FFF', fontSize: 14, fontWeight: '900' },
  dirBadge: { fontSize: 11, fontWeight: '800' },
  buyText: { color: '#10B981' },
  sellText: { color: '#EF4444' },
  statusBadge: { fontSize: 10, fontWeight: '800', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  pendingStatus: { backgroundColor: '#262626', color: '#999' },
  tpStatus: { backgroundColor: 'rgba(16,185,129,0.2)', color: '#10B981' },
  slStatus: { backgroundColor: 'rgba(239,68,68,0.2)', color: '#EF4444' },
  levelsRow: { flexDirection: 'row', justifyContent: 'space-between', marginVertical: 6 },
  levelText: { color: '#777', fontSize: 11 },
  boldWhite: { color: '#FFF', fontWeight: '800' },
  boldRed: { color: '#EF4444', fontWeight: '800' },
  boldGreen: { color: '#10B981', fontWeight: '800' },
  noteText: { color: '#888', fontSize: 11, marginTop: 4, lineHeight: 15 },
  outcomeRow: { flexDirection: 'row', gap: 6, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#242424' },
  outcomeBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 6, borderRadius: 8 },
  tpBtn: { backgroundColor: '#059669' },
  slBtn: { backgroundColor: '#DC2626' },
  outcomeBtnText: { color: '#FFF', fontSize: 10, fontWeight: '800' }
});
