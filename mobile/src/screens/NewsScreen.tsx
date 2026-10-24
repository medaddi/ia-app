import React, { useState, useEffect } from 'react';
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
import { Radio, AlertOctagon, ShieldCheck, Clock, Newspaper } from 'lucide-react-native';
import { fetchLiveNewsDirect, MobileNewsItem } from '../services/liveNewsClient';

export const NewsScreen: React.FC = () => {
  const [news, setNews] = useState<MobileNewsItem[]>([]);
  const [selectedCat, setSelectedCat] = useState<string>('ALL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadNews = async () => {
    try {
      const items = await fetchLiveNewsDirect();
      setNews(items);
    } catch (e) {
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadNews();
    const interval = setInterval(loadNews, 45000);
    return () => clearInterval(interval);
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    await loadNews();
  };

  const filtered = news.filter((item) => {
    if (selectedCat === 'ALL') return true;
    return item.category === selectedCat;
  });

  const hasLockout = news.some(n => n.isLockout);

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Newspaper size={20} color="#C5A059" />
          <Text style={styles.headerTitle}>الأخبار الاقتصادية المباشرة 24/7</Text>
        </View>
        <View style={styles.liveTag}>
          <View style={styles.liveDot} />
          <Text style={styles.liveTagText}>LIVE RSS</Text>
        </View>
      </View>

      <ScrollView
        style={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#C5A059" />}
      >
        {/* Macro Sentinel Banner */}
        <View style={[styles.sentinelBanner, hasLockout && styles.sentinelLockout]}>
          {hasLockout ? (
            <AlertOctagon size={18} color="#F87171" />
          ) : (
            <ShieldCheck size={18} color="#34D399" />
          )}
          <View style={styles.sentinelContent}>
            <Text style={[styles.sentinelTitle, hasLockout && styles.sentinelTitleLockout]}>
              {hasLockout
                ? '⛔ بروتوكول حظر التداول نشط (News Lockout)'
                : '🟢 المحيط الاقتصادي مستقر (Clear to Trade)'}
            </Text>
            <Text style={styles.sentinelDesc}>
              {hasLockout
                ? 'تم رصد بيانات شديدة الخطورة أو تقلبات عنيفة. محرك الصفقات يرفض الدخول لحماية الحساب.'
                : 'لا توجد أخبار معاكسة. الصفقات المؤسساتية مصرح بتنفيذها مع إدارة مخاطر 1%.'}
            </Text>
          </View>
        </View>

        {/* Categories */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.catScroll}>
          {[
            { id: 'ALL', label: 'الكل' },
            { id: 'fed', label: 'الفيدرالي' },
            { id: 'cpi', label: 'التضخم (CPI)' },
            { id: 'commodities', label: 'الذهب والنفط' },
            { id: 'geopolitical', label: 'الأزمات' }
          ].map((cat) => (
            <TouchableOpacity
              key={cat.id}
              style={[styles.catPill, selectedCat === cat.id && styles.catPillActive]}
              onPress={() => setSelectedCat(cat.id)}
            >
              <Text style={[styles.catText, selectedCat === cat.id && styles.catTextActive]}>
                {cat.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* News Items */}
        {loading ? (
          <View style={styles.loadingBox}>
            <ActivityIndicator size="large" color="#C5A059" />
            <Text style={styles.loadingText}>جاري استلام الأخبار المباشرة...</Text>
          </View>
        ) : (
          filtered.map((item) => {
            const isLock = item.isLockout;
            return (
              <View key={item.id} style={[styles.newsCard, isLock && styles.newsCardLockout]}>
                <View style={styles.cardMeta}>
                  <View style={styles.badgeRow}>
                    <Text style={[styles.impactBadge, isLock && styles.impactBadgeLockout]}>
                      {isLock ? '⛔ LOCKOUT' : `${item.importance} IMPACT`}
                    </Text>
                    {item.impactAsset && (
                      <Text style={styles.assetBadge}>{item.impactAsset}</Text>
                    )}
                  </View>
                  <Text style={styles.timeSource}>
                    {item.timeAgo} • {item.source}
                  </Text>
                </View>

                <Text style={styles.headlineText}>
                  {item.titleAr || item.title}
                </Text>

                <Text style={styles.reasonText}>
                  {item.reasonAr || item.reasonEn}
                </Text>
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#242424'
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { color: '#FFF', fontSize: 14, fontWeight: '800' },
  liveTag: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(197, 160, 89, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8
  },
  liveDot: { width: 5, height: 5, borderRadius: 2.5, backgroundColor: '#C5A059' },
  liveTagText: { color: '#C5A059', fontSize: 9, fontWeight: '800' },
  scroll: { flex: 1, padding: 14 },
  sentinelBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#161616',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(52, 211, 153, 0.3)',
    padding: 12,
    marginBottom: 14
  },
  sentinelLockout: {
    backgroundColor: 'rgba(248, 113, 113, 0.08)',
    borderColor: 'rgba(248, 113, 113, 0.35)'
  },
  sentinelContent: { flex: 1 },
  sentinelTitle: { color: '#34D399', fontSize: 12, fontWeight: '800' },
  sentinelTitleLockout: { color: '#F87171' },
  sentinelDesc: { color: '#888', fontSize: 10, marginTop: 2, lineHeight: 14 },
  catScroll: { gap: 6, marginBottom: 14 },
  catPill: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 10,
    backgroundColor: '#1E1E1E',
    borderWidth: 1,
    borderColor: '#2A2A2A'
  },
  catPillActive: { backgroundColor: '#C5A059', borderColor: '#C5A059' },
  catText: { color: '#888', fontSize: 11, fontWeight: '700' },
  catTextActive: { color: '#121212', fontWeight: '900' },
  newsCard: {
    backgroundColor: '#181818',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    marginBottom: 10
  },
  newsCardLockout: { borderColor: 'rgba(248, 113, 113, 0.35)' },
  cardMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8
  },
  badgeRow: { flexDirection: 'row', gap: 6 },
  impactBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    color: '#FBBF24',
    fontSize: 9,
    fontWeight: '800',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4
  },
  impactBadgeLockout: { backgroundColor: 'rgba(248, 113, 113, 0.2)', color: '#F87171' },
  assetBadge: {
    backgroundColor: 'rgba(197, 160, 89, 0.15)',
    color: '#C5A059',
    fontSize: 9,
    fontWeight: '800',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4
  },
  timeSource: { color: '#777', fontSize: 10 },
  headlineText: { color: '#FFF', fontSize: 13, fontWeight: '800', lineHeight: 18, marginBottom: 6 },
  reasonText: { color: '#999', fontSize: 11, lineHeight: 16 },
  loadingBox: { padding: 40, alignItems: 'center' },
  loadingText: { color: '#888', marginTop: 10, fontSize: 11 }
});
