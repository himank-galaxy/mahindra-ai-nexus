import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Panel({
  children,
  className,
  title,
  actions,
  subtitle,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div
      className={cn("glass rounded-2xl p-5 shadow-[0_10px_40px_-20px_rgba(0,0,0,0.6)]", className)}
    >
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && (
              <h3 className="text-sm font-semibold tracking-wide text-foreground/90 uppercase">
                {title}
              </h3>
            )}
            {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatPill({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  const map: Record<string, string> = {
    default: "bg-white/5 text-foreground/80 border-white/10",
    success: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    warning: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    danger: "bg-red-500/10 text-red-300 border-red-500/30",
    info: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase",
        map[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const w = 120,
    h = 30;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / (max - min || 1)) * h;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("h-8 w-full", className)}>
      <polyline
        points={pts}
        fill="none"
        stroke="url(#g)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <defs>
        <linearGradient id="g" x1="0" x2="1">
          <stop offset="0" stopColor="oklch(0.72 0.22 27)" />
          <stop offset="1" stopColor="oklch(0.85 0.05 260)" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function MiniBar({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3">
          <div className="w-28 text-xs text-muted-foreground truncate">{d.label}</div>
          <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full mahindra-gradient rounded-full transition-all"
              style={{ width: `${(d.value / max) * 100}%` }}
            />
          </div>
          <div className="w-10 text-right text-xs font-semibold">{d.value}</div>
        </div>
      ))}
    </div>
  );
}

export function SectionTitle({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-gradient-mahindra">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
