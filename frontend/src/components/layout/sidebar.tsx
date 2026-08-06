import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  BookOpen,
  FlaskConical,
  Car,
  Store,
  Landmark,
  Users,
  Truck,
  Recycle,
  Sparkles,
  ShieldCheck,
  Bot,
  MessageSquareCode,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Executive Overview", icon: LayoutDashboard },
  { to: "/catalogue", label: "AI Solution Catalogue", icon: BookOpen },
  { to: "/simulation", label: "Simulation Center", icon: FlaskConical },
  { to: "/mobility-twin", label: "Auto Mobility Twin", icon: Car },
  { to: "/dealer", label: "Dealer Revenue Optimizer", icon: Store },
  { to: "/finance", label: "Financial Services", icon: Landmark },
  { to: "/collections", label: "Collections AI Swarm", icon: Users },
  { to: "/logistics", label: "Logistics Control Tower", icon: Truck },
  { to: "/circularity", label: "Circular Economy", icon: Recycle },
  { to: "/xr", label: "AR/VR Experience", icon: Sparkles },
  { to: "/trust", label: "Compliance Trust Ledger", icon: ShieldCheck },
  { to: "/agents", label: "AI Factory Agents", icon: Bot },
  { to: "/copilot", label: "Analytics Copilot", icon: MessageSquareCode },
];

export function Sidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-white/5 bg-sidebar/95 backdrop-blur-xl lg:flex">
      <div className="flex h-16 items-center gap-3 border-b border-white/5 px-5">
        <div className="grid h-9 w-9 place-items-center rounded-lg mahindra-gradient shadow-lg shadow-red-900/30">
          <span className="text-sm font-bold tracking-tight text-white">M</span>
        </div>
        <div className="leading-tight">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Mahindra</div>
          <div className="text-sm font-semibold">AI Command Center</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {NAV.map((item) => {
          const active = pathname === item.to;
          const Icon = item.icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all",
                active
                  ? "bg-primary/15 text-foreground shadow-inner shadow-primary/10"
                  : "text-sidebar-foreground/80 hover:bg-white/5 hover:text-foreground",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0 transition-colors",
                  active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                )}
              />
              <span className="truncate">{item.label}</span>
              {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary pulse-red" />}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-white/5 p-4">
        <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Closed-loop AI
          </div>
          <div className="mt-1 text-xs font-medium">Predict · Explain · Simulate · Act · Learn</div>
        </div>
      </div>
    </aside>
  );
}
