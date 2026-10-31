import React from 'react';
import { SentimentData, Language } from '../types';
import { Compass, MessageSquare, Twitter, Globe, Flame } from 'lucide-react';

interface SentimentProps {
  sentiment: SentimentData | null;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const SentimentRadar: React.FC<SentimentProps> = ({ sentiment, lang, theme = 'light' }) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  if (!sentiment) return null;

  return (
    <div className={`rounded-2xl border p-5 shadow-sm transition-colors ${
      isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'
    }`}>
      {/* Header */}
      <div className={`flex items-center justify-between pb-4 mb-4 border-b ${
        isLight ? 'border-paper-line-2' : 'border-line'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-xl border flex items-center justify-center shadow-xs ${
            isLight ? 'bg-paper border-gold-200 text-gold-700' : 'bg-surface border-gold-700 text-gold-400'
          }`}>
            <Compass className="w-4 h-4" />
          </div>
          <div>
            <h3 className={`font-bold text-sm flex items-center gap-2 ${isLight ? 'text-ink-strong' : 'text-white'}`}>
              <span>{isFr ? 'Radar de Sentiment & Flux Social' : isAr ? 'تحليل المشاعر والتدفق المؤسساتي' : 'Sentiment Radar & Flow'}</span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${
                isLight ? 'bg-paper text-gold-700 border-gold-200' : 'bg-surface-2 text-gold-400 border-gold-700'
              }`}>
                Institutional Aggregate
              </span>
            </h3>
            <p className={`text-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
              {isFr ? 'Agrégation des positions institutionnelles et sentiment retail' : isAr ? 'قياس مزاج السوق وتمركزات السيولة المؤسساتية' : 'Aggregated market positioning & institutional sentiment'}
            </p>
          </div>
        </div>

        {/* Fear & Greed Index */}
        <div className="text-right">
          <div className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
            {isFr ? 'Indice Fear & Greed' : isAr ? 'مؤشر الخوف والطمع' : 'Fear & Greed Index'}
          </div>
          <div className="flex items-center gap-1.5 justify-end mt-0.5">
            <Flame className="w-4 h-4 text-gold-500 animate-pulse" />
            <span className={`text-base font-black font-mono-numbers ${isLight ? 'text-gold-700' : 'text-gold-400'}`}>
              {sentiment.fearAndGreedIndex}/100
            </span>
            <span className={`text-xs font-medium ${isLight ? 'text-slate-600' : 'text-slate-300'}`}>({sentiment.fearAndGreedLabel})</span>
          </div>
        </div>
      </div>

      {/* Main Breakdown */}
      <div className={`p-4 rounded-xl border mb-4 ${
        isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
      }`}>
        <div className="flex items-center justify-between mb-2">
          <span className={`text-xs font-bold uppercase tracking-wide ${isLight ? 'text-ink-strong' : 'text-slate-200'}`}>
            {sentiment.assetSymbol} {isFr ? 'Sentiment Global :' : isAr ? 'معنويات عامة:' : 'Overall Sentiment:'}
          </span>
          <span className={`text-xs font-mono-numbers font-bold ${isLight ? 'text-gold-700' : 'text-gold-400'}`}>
            {sentiment.positive}% Bullish
          </span>
        </div>

        {/* Triple-color bar */}
        <div className={`w-full h-3 rounded-full overflow-hidden flex mb-3 ${isLight ? 'bg-paper' : 'bg-surface-3'}`}>
          <div
            className="bg-emerald-500 h-full transition-all"
            style={{ width: `${sentiment.positive}%` }}
            title={`Positive: ${sentiment.positive}%`}
          />
          <div
            className={isLight ? 'bg-slate-300 h-full transition-all' : 'bg-slate-700 h-full transition-all'}
            style={{ width: `${sentiment.neutral}%` }}
            title={`Neutral: ${sentiment.neutral}%`}
          />
          <div
            className="bg-rose-500 h-full transition-all"
            style={{ width: `${sentiment.negative}%` }}
            title={`Negative: ${sentiment.negative}%`}
          />
        </div>

        <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono-numbers">
          <div className={`p-2 rounded-lg border ${
            isLight ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-emerald-950/40 border-emerald-800/30 text-emerald-300'
          }`}>
            <span className="text-xs block font-semibold">{isFr ? 'Haussier' : isAr ? 'إيجابي' : 'Positive'}</span>
            <span className="text-sm font-bold">{sentiment.positive}%</span>
          </div>
          <div className={`p-2 rounded-lg border ${
            isLight ? 'bg-slate-100 border-slate-200 text-slate-700' : 'bg-slate-900 border-slate-800 text-slate-300'
          }`}>
            <span className="text-xs block font-semibold">{isFr ? 'Neutre' : isAr ? 'محايد' : 'Neutral'}</span>
            <span className="text-sm font-bold">{sentiment.neutral}%</span>
          </div>
          <div className={`p-2 rounded-lg border ${
            isLight ? 'bg-rose-50 border-rose-200 text-rose-800' : 'bg-rose-950/40 border-rose-800/30 text-rose-300'
          }`}>
            <span className="text-xs block font-semibold">{isFr ? 'Baissier' : isAr ? 'سلبي' : 'Negative'}</span>
            <span className="text-sm font-bold">{sentiment.negative}%</span>
          </div>
        </div>
      </div>
    </div>
  );
};
