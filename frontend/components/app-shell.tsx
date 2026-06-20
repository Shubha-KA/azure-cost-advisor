"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  Bot,
  ChartNoAxesCombined,
  LayoutDashboard,
  Lightbulb,
  Moon,
  Settings,
  Sun,
  Boxes,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useScope } from "@/components/scope-provider";

const links = [
  ["/dashboard", "Dashboard", LayoutDashboard],
  ["/costs", "Cost analytics", ChartNoAxesCombined],
  ["/resources", "Resource inventory", Boxes],
  ["/recommendations", "Recommendations", Lightbulb],
  ["/assistant", "AI assistant", Bot],
  ["/admin", "Administration", Settings],
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Bypass the app shell for standalone pages (login, onboarding)
  if (pathname === "/login") {
    return <>{children}</>;
  }

  return <AppShellInner>{children}</AppShellInner>;
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { scope, tenants, subscriptions, setTenant, setSubscription } =
    useScope();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className="fixed inset-y-0 hidden w-64 border-r bg-card p-5 lg:block">
        <div className="mb-8 text-lg font-semibold">Azure Cost Advisor</div>
        <nav className="space-y-1">
          {links.map(([href, label, Icon]) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted",
                pathname === href && "bg-muted font-medium text-foreground",
              )}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="absolute bottom-5 left-5 text-xs text-muted-foreground">
          Streamlit remains available as Legacy Admin UI
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b bg-background/90 px-4 py-3 backdrop-blur md:px-8">
          {tenants.length > 0 && (
            <select
              aria-label="Tenant"
              className="rounded-lg border bg-background px-3 py-2 text-sm disabled:opacity-50"
              value={scope.tenantId}
              onChange={(event) => setTenant(event.target.value)}
              disabled={tenants.length === 0}
            >
              {tenants.map((item) => (
                <option key={item.tenantId} value={item.tenantId}>
                  {item.displayName || item.tenantId}
                </option>
              ))}
            </select>
          )}
          {subscriptions.length > 0 && (
            <select
              aria-label="Subscription"
              className="rounded-lg border bg-background px-3 py-2 text-sm disabled:opacity-50"
              value={scope.subscriptionId}
              onChange={(event) => setSubscription(event.target.value)}
              disabled={subscriptions.length === 0}
            >
              {subscriptions.map((item) => (
                <option key={item.subscriptionId} value={item.subscriptionId}>
                  {item.displayName || item.subscriptionId}
                </option>
              ))}
            </select>
          )}
          <button
            aria-label="Toggle theme"
            className="ml-auto rounded-lg border p-2"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button
            aria-label="Sign out"
            className="rounded-lg border p-2 text-muted-foreground hover:bg-muted"
            onClick={() => window.location.href = "/api/auth/logout"}
            title="Sign Out"
          >
            <LogOut size={18} />
          </button>
        </header>
        <main className="p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}

