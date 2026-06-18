"use client";

import { api, Scope } from "@/lib/api";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

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

  useEffect(() => {
    api<Entity[]>("/api/tenants")
      .then((items) => {
        setTenants(items);
        const tenantId =
          localStorage.getItem("tenantId") || items[0]?.tenantId || "";
        setScope((value) => ({ ...value, tenantId }));
      })
      .catch(() => setTenants([]));
  }, []);

  useEffect(() => {
    if (!scope.tenantId) return;
    api<Entity[]>("/api/subscriptions", {
      tenantId: scope.tenantId,
      subscriptionId: "",
    })
      .then((items) => {
        setSubscriptions(items);
        const subscriptionId =
          localStorage.getItem("subscriptionId") ||
          items[0]?.subscriptionId ||
          "";
        setScope((value) => ({ ...value, subscriptionId }));
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
