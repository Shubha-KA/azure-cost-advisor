"use client";

import { api, Scope } from "@/lib/api";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname } from "next/navigation";

type Entity = { tenantId: string; subscriptionId?: string; displayName?: string };
type ScopeContextValue = {
  scope: Scope;
  tenants: Entity[];
  subscriptions: Entity[];
  setTenant: (id: string) => void;
  setSubscription: (id: string) => void;
};

const ScopeContext = createContext<ScopeContextValue | null>(null);

export function ScopeProvider({ children }: { children: React.ReactNode }) {
  const [tenants, setTenants] = useState<Entity[]>([]);
  const [subscriptions, setSubscriptions] = useState<Entity[]>([]);
  const [scope, setScope] = useState<Scope>({
    tenantId: "",
    subscriptionId: "",
  });
  const pathname = usePathname();
  const isPublicPage = pathname === "/" || pathname === "/login";

  useEffect(() => {
    if (isPublicPage) return;
    api<Entity[]>("/api/tenants")
      .then((items) => {
        setTenants(items);
        let tenantId = localStorage.getItem("tenantId");
        if (!items.find((i) => i.tenantId === tenantId)) {
          tenantId = items[0]?.tenantId || "";
        }
        setScope((value) => ({ ...value, tenantId: tenantId as string }));
      })
      .catch(() => setTenants([]));
  }, [isPublicPage]);

  useEffect(() => {
    if (!scope.tenantId) return;
    api<Entity[]>("/api/subscriptions", {
      tenantId: scope.tenantId,
      subscriptionId: "",
    })
      .then((items) => {
        setSubscriptions(items);
        let subscriptionId = localStorage.getItem("subscriptionId");
        if (!items.find((i) => i.subscriptionId === subscriptionId)) {
          subscriptionId = items[0]?.subscriptionId || "";
        }
        setScope((value) => ({ ...value, subscriptionId: subscriptionId as string }));
      })
      .catch(() => setSubscriptions([]));
  }, [scope.tenantId]);

  const value = useMemo(
    () => ({
      scope,
      tenants,
      subscriptions,
      setTenant: (tenantId: string) => {
        localStorage.setItem("tenantId", tenantId);
        setScope({ tenantId, subscriptionId: "" });
      },
      setSubscription: (subscriptionId: string) => {
        localStorage.setItem("subscriptionId", subscriptionId);
        setScope((current) => ({ ...current, subscriptionId }));
      },
    }),
    [scope, tenants, subscriptions],
  );
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope() {
  const value = useContext(ScopeContext);
  if (!value) throw new Error("useScope must be used within ScopeProvider");
  return value;
}
