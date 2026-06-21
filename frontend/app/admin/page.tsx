"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { Card } from "@/components/ui/card";

type Subscription = { subscriptionId: string; displayName: string; onboardingStatus: string; status: string };

export default function Admin() {
  const { scope } = useScope();
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [metrics, setMetrics] = useState<Record<string, unknown>>({});
  useEffect(() => {
    if (!scope.tenantId) return;
    api<Subscription[]>("/api/subscriptions", scope).then(setSubscriptions);
    api<Record<string, unknown>>("/api/metrics", scope).then(setMetrics).catch(() => setMetrics({ status: "Metrics disabled" }));
  }, [scope]);
  return (
    <>
      <PageHeader title="Administration" description="Tenant settings, subscriptions, RBAC health, and API operations." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card><h2 className="mb-3 font-semibold">Subscriptions</h2>{subscriptions.map((item) => <div key={item.subscriptionId} className="border-t py-3 text-sm"><div className="font-medium">{item.displayName || item.subscriptionId}</div><div className="text-muted-foreground">{item.onboardingStatus} · {item.status}</div></div>)}</Card>
        <Card><h2 className="mb-3 font-semibold">API observability</h2><pre className="overflow-auto text-xs">{JSON.stringify(metrics, null, 2)}</pre></Card>
      </div>
    </>
  );
}
