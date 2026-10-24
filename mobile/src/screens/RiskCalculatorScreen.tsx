import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { Calculator, ShieldCheck, Save } from 'lucide-react-native';
import { loadUserSettings, saveUserSettings } from '../services/localDatabase';

export const RiskCalculatorScreen: React.FC = () => {
  const [balance, setBalance] = useState('10000');
  const [riskPct, setRiskPct] = useState('1.0');
  const [slPips, setSlPips] = useState('35');
  const [pipValue, setPipValue] = useState('10');
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    async function load() {
      const sets = await loadUserSettings();
      setBalance(sets.accountBalance.toString());
      setRiskPct(sets.riskPerTrade.toString());
    }
    load();
  }, []);

  const numBalance = parseFloat(balance) || 10000;
  const numRiskPct = parseFloat(riskPct) || 1.0;
  const numSlPips = parseFloat(slPips) || 35;
  const numPipVal = parseFloat(pipValue) || 10;

  const riskAmountUsd = numBalance * (numRiskPct / 100);
  const lotSize = Math.max(0.01, Number((riskAmountUsd / (numSlPips * numPipVal)).toFixed(2)));

  const handleSavePreferences = async () => {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    await saveUserSettings({
      accountBalance: numBalance,
      riskPerTrade: numRiskPct
    });
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Calculator size={20} color="#C5A059" />
          <Text style={styles.headerTitle}>حاسبة إدارة المخاطر المؤسساتية 1%</Text>
        </View>
      </View>

      <ScrollView style={styles.scroll}>
        {/* Output Card */}
        <View style={styles.resultCard}>
          <Text style={styles.resultLabel}>حجم اللوت المقترح بدقة (Position Size)</Text>
          <Text style={styles.resultValue}>{lotSize} <Text style={styles.resultUnit}>Lots</Text></Text>

          <View style={styles.resultMetaRow}>
            <View>
              <Text style={styles.metaLabel}>المبلغ المعرض للمخاطرة</Text>
              <Text style={styles.metaValue}>${riskAmountUsd.toFixed(1)}</Text>
            </View>
            <View>
              <Text style={styles.metaLabel}>الربح المستهدف (1:3.5)</Text>
              <Text style={[styles.metaValue, styles.profitGreen]}>+${(riskAmountUsd * 3.5).toFixed(1)}</Text>
            </View>
          </View>
        </View>

        {/* Inputs */}
        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>رصيد الحساب ($ USD)</Text>
          <TextInput
            style={styles.input}
            keyboardType="numeric"
            value={balance}
            onChangeText={setBalance}
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>نسبة المخاطرة لكل صفقة (Risk %)</Text>
          <View style={styles.presetRow}>
            {['0.5', '1.0', '1.5', '2.0'].map((p) => (
              <TouchableOpacity
                key={p}
                style={[styles.presetBtn, riskPct === p && styles.presetBtnActive]}
                onPress={() => setRiskPct(p)}
              >
                <Text style={[styles.presetText, riskPct === p && styles.presetTextActive]}>{p}%</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>مسافة الستوب بالنقاط (SL Pips)</Text>
          <TextInput
            style={styles.input}
            keyboardType="numeric"
            value={slPips}
            onChangeText={setSlPips}
          />
        </View>

        <TouchableOpacity style={styles.saveBtn} onPress={handleSavePreferences}>
          <Save size={16} color="#121212" />
          <Text style={styles.saveBtnText}>
            {savedSuccess ? 'تم حفظ الإعدادات محلياً بنجاح ✓' : 'حفظ الإعدادات في ذاكرة الهاتف (Save)'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#121212', paddingTop: 50 },
  header: { paddingHorizontal: 16, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#242424' },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { color: '#FFF', fontSize: 13, fontWeight: '800' },
  scroll: { flex: 1, padding: 16 },
  resultCard: {
    backgroundColor: '#1E1E1E',
    borderRadius: 16,
    padding: 18,
    borderWidth: 1,
    borderColor: '#C5A059',
    alignItems: 'center',
    marginBottom: 20
  },
  resultLabel: { color: '#C5A059', fontSize: 11, fontWeight: '700', marginBottom: 4 },
  resultValue: { color: '#FFF', fontSize: 36, fontWeight: '900' },
  resultUnit: { fontSize: 16, color: '#AAA' },
  resultMetaRow: { flexDirection: 'row', justifyContent: 'space-between', width: '100%', marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: '#2C2C2C' },
  metaLabel: { color: '#777', fontSize: 10 },
  metaValue: { color: '#FFF', fontSize: 14, fontWeight: '800', marginTop: 2 },
  profitGreen: { color: '#10B981' },
  inputGroup: { marginBottom: 16 },
  inputLabel: { color: '#999', fontSize: 11, marginBottom: 6, fontWeight: '600' },
  input: {
    backgroundColor: '#181818',
    borderRadius: 12,
    padding: 12,
    color: '#FFF',
    fontSize: 15,
    fontWeight: '800',
    borderWidth: 1,
    borderColor: '#2A2A2A'
  },
  presetRow: { flexDirection: 'row', gap: 8 },
  presetBtn: { flex: 1, paddingVertical: 10, backgroundColor: '#181818', borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: '#2A2A2A' },
  presetBtnActive: { backgroundColor: '#C5A059', borderColor: '#C5A059' },
  presetText: { color: '#888', fontWeight: '800', fontSize: 12 },
  presetTextActive: { color: '#121212', fontWeight: '900' },
  saveBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#C5A059', paddingVertical: 14, borderRadius: 12, marginTop: 10 },
  saveBtnText: { color: '#121212', fontSize: 13, fontWeight: '900' }
});
