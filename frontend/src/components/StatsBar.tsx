import { BarChart3, CheckCircle2, AlertTriangle, Percent } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { ReviewResult } from "@/types";

interface StatsBarProps {
  results: ReviewResult[];
}

export function StatsBar({ results }: StatsBarProps) {
  if (results.length === 0) return null;

  const total = results.length;
  const flagged = results.filter((r) => r.flags.length > 0).length;
  const clean = total - flagged;
  const cleanPct = total ? ((clean / total) * 100).toFixed(1) : "0";

  /* Collect all unique flags and count */
  const flagCounts: Record<string, number> = {};
  for (const r of results) {
    for (const f of r.flags) {
      flagCounts[f] = (flagCounts[f] || 0) + 1;
    }
  }
  const topFlags = Object.entries(flagCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="animate-slide-up space-y-3">
      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          icon={<BarChart3 className="h-4 w-4 text-blue-500" />}
          label="Total Reviewed"
          value={total.toString()}
          accent="blue"
        />
        <StatCard
          icon={<CheckCircle2 className="h-4 w-4 text-emerald-500" />}
          label="Clean"
          value={clean.toString()}
          accent="emerald"
        />
        <StatCard
          icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
          label="Flagged"
          value={flagged.toString()}
          accent="amber"
        />
        <StatCard
          icon={<Percent className="h-4 w-4 text-violet-500" />}
          label="Clean Rate"
          value={`${cleanPct}%`}
          accent="violet"
        />
      </div>

      {/* Top Flags breakdown */}
      {topFlags.length > 0 && (
        <Card>
          <CardContent className="p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Top Flags
            </p>
            <div className="space-y-2">
              {topFlags.map(([flag, count]) => {
                const pct = ((count / total) * 100).toFixed(0);
                return (
                  <div key={flag} className="flex items-center gap-3">
                    <span className="w-36 truncate text-sm font-medium">{flag}</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all duration-700"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-16 text-right text-xs text-muted-foreground">
                      {count} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="relative p-4">
        {/* Subtle gradient accent */}
        <div
          className={`absolute inset-0 opacity-[0.04] bg-gradient-to-br from-${accent}-500 to-transparent`}
        />
        <div className="relative flex items-center gap-2.5">
          <div className={`flex h-8 w-8 items-center justify-center rounded-lg bg-${accent}-100 dark:bg-${accent}-950`}>
            {icon}
          </div>
          <div>
            <p className="text-xl font-bold tracking-tight">{value}</p>
            <p className="text-[11px] text-muted-foreground">{label}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
