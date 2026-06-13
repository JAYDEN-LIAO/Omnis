'use client';

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import type { VolumeStats } from '@/lib/api';

// Gold theme color palette
const KW_COLORS = [
  'oklch(0.78 0.16 85)',
  'oklch(0.74 0.15 85)',
  'oklch(0.7 0.14 85)',
  'oklch(0.65 0.13 85)',
  'oklch(0.6 0.12 85)',
];
const NEG_COLOR = 'oklch(0.55 0.18 25)';

interface VolumeChartProps {
  data: VolumeStats;
}

export function VolumeChart({ data }: VolumeChartProps) {
  const chartData = data.days.map((d, i) => ({
    day: d,
    总声量: data.volumes[i] ?? 0,
    负面: data.negative_volumes[i] ?? 0,
    ...Object.fromEntries(
      Object.entries(data.keywords_volumes ?? {}).map(([kw, vols]) => [kw, vols[i] ?? 0]),
    ),
  }));

  const keywords = Object.keys(data.keywords_volumes ?? {});
  const hasKeywords = keywords.length > 0;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={chartData} margin={{ top: 10, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="gradTotal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={KW_COLORS[0]} stopOpacity={0.3} />
            <stop offset="100%" stopColor={KW_COLORS[0]} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gradNeg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={NEG_COLOR} stopOpacity={0.25} />
            <stop offset="100%" stopColor={NEG_COLOR} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-faint)" />
        <XAxis dataKey="day" tick={{ fill: 'var(--on-surface-variant)', fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: 'var(--on-surface-variant)', fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{
            background: 'var(--surface-card-strong)',
            backdropFilter: 'blur(12px)',
            border: '0.5px solid var(--border-refined)',
            borderRadius: 8,
            color: 'var(--on-surface)',
            fontSize: 12,
          }}
        />
        <Area type="monotone" dataKey="总声量" stroke={KW_COLORS[0]} strokeWidth={2} fill="url(#gradTotal)" name="总声量" />
        <Area type="monotone" dataKey="负面" stroke={NEG_COLOR} strokeWidth={2} fill="url(#gradNeg)" name="负面" />
        {hasKeywords && keywords.map((kw, idx) => (
          <Area
            key={kw}
            type="monotone"
            dataKey={kw}
            stroke={KW_COLORS[Math.min(idx + 1, KW_COLORS.length - 1)]}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            fill="none"
            name={kw}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface PieDatum {
  name: string;
  value: number;
  color: string;
}

export function RiskPieChart({ data }: { data: PieDatum[] }) {
  const nonZero = data.filter(d => d.value > 0);
  const safeData = nonZero.length > 0 ? nonZero : [{ name: '暂无数据', value: 1, color: 'var(--border-faint)' }];

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={safeData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} paddingAngle={3}>
          {safeData.map((entry) => (
            <Cell key={entry.name} fill={entry.color} stroke="none" />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: 'var(--surface-card-strong)',
            backdropFilter: 'blur(12px)',
            border: '0.5px solid var(--border-refined)',
            borderRadius: 8,
            color: 'var(--on-surface)',
            fontSize: 12,
          }}
        />
        <Legend
          iconType="circle"
          wrapperStyle={{ fontSize: 11, color: 'var(--on-surface-variant)' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
