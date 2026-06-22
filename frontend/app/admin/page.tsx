"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/finops-ui";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { Card } from "@/components/ui/card";
import { StatusPill, TableSkeleton } from "@/components/ux";

type Subscription = {
  subscriptionId: string;
  displayName: string;
  onboardingStatus: string;
  status: string;
  tenantId: string;
};
type TenantHealth = {
  subscriptionId: string;
  validationStatus: string;
  validationResults: Record<string, { name: string; status: string; message?: string }>;
  lastChecked: string;
};
type OnboardingStatus = {
  status: string;
  subscriptions?: {
    collection?: {
      status?: string;
      completedAt?: string;
      recordsCollected?: number;
      counts?: Record<string, number>;
    };
    processing?: {
      status?: string;
      completedAt?: string;
      recordCounts?: Record<string, number>;
    };
  }[];
};

const requiredPermissions = [
  ["subscriptionAccess", "Reader"],
  ["costManagement", "Cost Management Reader"],
  ["advisor", "Advisor Reader"],
  ["monitor", "Monitoring Reader"],
  ["resourceGraph", "Resource Graph Access"],
] as const;

export default function Admin() {
  const { scope } = useScope();
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [health, setHealth] = useState<TenantHealth[]>([]);
  const [onboarding, setOnboarding] = useState<OnboardingStatus>();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!scope.tenantId) return;
    setLoading(true);
    Promise.all([
      api<Subscription[]>("/api/subscriptions", scope),
      api<TenantHealth[]>("/api/tenant-health", scope),
      api<OnboardingStatus>("/api/onboarding/status", scope),
    ])
      .then(([subs, healthRows, onboardingStatus]) => {
        setSubscriptions(subs);
        setHealth(healthRows);
        setOnboarding(onboardingStatus);
      })
      .finally(() => setLoading(false));
  }, [scope]);

  const selected = subscriptions.find((item) => item.subscriptionId === scope.subscriptionId) || subscriptions[0];
  const healthRow = health.find((item) => item.subscriptionId === selected?.subscriptionId) || health[0];
  const pipeline = onboarding?.subscriptions?.[0];

  return (
    <>
      <PageHeader title="Administration" description="Tenant operations, permission posture, collection status, and system health." />
      {loading ? (
        <TableSkeleton rows={8} columns={4} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card className="p-5">
            <h2 className="text-lg font-semibold">Subscription Overview</h2>
            <div className="mt-5 space-y-4">
              {subscriptions.map((item) => (
                <div key={item.subscriptionId} className="rounded-xl border bg-background/40 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{item.displayName || item.subscriptionId}</div>
                      <div className="mt-1 break-all text-xs text-muted-foreground">{item.subscriptionId}</div>
                    </div>
                    <StatusPill label={item.status} tone={item.status === "Enabled" ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500"} />
                  </div>
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                    <Info label="Tenant" value={item.tenantId} />
                    <Info label="Onboarding" value={item.onboardingStatus} />
                  </dl>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-lg font-semibold">Permission Status</h2>
            <p className="mt-1 text-sm text-muted-foreground">RBAC and API validation for the selected subscription.</p>
            <div className="mt-5 space-y-3">
              {requiredPermissions.map(([key, label]) => {
                const result = healthRow?.validationResults?.[key];
                const granted = result?.status === "passed";
                return (
                  <div key={key} className="flex items-center justify-between gap-4 rounded-xl border bg-background/40 p-4">
                    <div>
                      <div className="font-medium">{label}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{result?.message || "Not validated"}</div>
                    </div>
                    <StatusPill label={granted ? "Granted" : "Missing"} tone={granted ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"} />
                  </div>
                );
              })}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-lg font-semibold">Collection Status</h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <InfoBox label="Last Collection" value={formatDateTime(pipeline?.collection?.completedAt)} />
              <InfoBox label="Last Processing" value={formatDateTime(pipeline?.processing?.completedAt)} />
              <InfoBox label="Records Collected" value={String(pipeline?.collection?.recordsCollected ?? 0)} />
              <InfoBox label="Records Processed" value={String(pipeline?.processing?.recordCounts?.costFacts ?? 0)} />
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-lg font-semibold">System Health</h2>
            <div className="mt-5 grid gap-3">
              <Service name="Auth Service" healthy={Boolean(scope.tenantId)} />
              <Service name="Collection Service" healthy={pipeline?.collection?.status === "completed"} />
              <Service name="Processing Service" healthy={pipeline?.processing?.status === "completed"} />
              <Service name="AI Service" healthy={true} />
              <Service name="API Gateway" healthy={true} />
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-all font-medium">{value || "Not available"}</dd>
    </div>
  );
}

function InfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-background/40 p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-2 font-semibold">{value}</div>
    </div>
  );
}

function Service({ name, healthy }: { name: string; healthy: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-xl border bg-background/40 p-4">
      <span className="font-medium">{name}</span>
      <StatusPill label={healthy ? "Healthy" : "Unhealthy"} tone={healthy ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"} />
    </div>
  );
}
