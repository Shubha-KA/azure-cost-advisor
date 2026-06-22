"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
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
import { api, logoutUrl } from "@/lib/api";

const links = [
  ["/dashboard", "Dashboard", LayoutDashboard],
  ["/costs", "Cost analytics", ChartNoAxesCombined],
  ["/resources", "Resource inventory", Boxes],
  ["/recommendations", "Recommendations", Lightbulb],
  ["/assistant", "AI assistant", Bot],
  ["/admin", "Administration", Settings],
] as const;

type CurrentUser = {
  tenant_id: string;
  user_id: string;
  email: string;
  display_name: string;
  roles: string[];
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Bypass the app shell for standalone public/auth pages.
  if (pathname === "/" || pathname === "/login") {
    return <>{children}</>;
  }

  return <AppShellInner>{children}</AppShellInner>;
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const { theme, setTheme } = useTheme();
  useEffect(() => { setMounted(true); }, []);
  const { scope, tenants, subscriptions, setTenant, setSubscription } =
    useScope();
  useEffect(() => {
    api<CurrentUser>("/api/auth/me")
      .then((user) => {
        setCurrentUser(user);
        const prior = localStorage.getItem("currentUserId");
        if (prior && prior !== user.user_id) {
          localStorage.removeItem("tenantId");
          localStorage.removeItem("subscriptionId");
        }
        localStorage.setItem("currentUserId", user.user_id);
      })
      .catch(() => setCurrentUser(null));
  }, []);
  const primaryRole = currentUser?.roles?.[0]?.replace(/_/g, " ") || "user";
  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className="fixed inset-y-0 hidden w-64 border-r bg-card p-5 lg:block">
        <div className="mb-8 text-lg font-semibold">FinsOpsIQ</div>
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
          {currentUser && (
            <div className="ml-auto hidden min-w-0 max-w-xs flex-col text-right md:flex">
              <span className="truncate text-sm font-medium">
                {currentUser.display_name || currentUser.email}
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {currentUser.email} · {primaryRole}
              </span>
            </div>
          )}
          <button
            aria-label="Toggle theme"
            className={cn("rounded-lg border p-2", !currentUser && "ml-auto")}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <div className="h-[18px] w-[18px]">
              {mounted && (theme === "dark" ? <Sun size={18} /> : <Moon size={18} />)}
            </div>
          </button>
          <button
            aria-label="Sign out"
            className="rounded-lg border p-2 text-muted-foreground hover:bg-muted"
            onClick={() => window.location.href = logoutUrl}
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
