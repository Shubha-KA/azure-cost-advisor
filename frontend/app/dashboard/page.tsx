"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { formatDateTime, formatMoney, freshnessLabel } from "@/lib/finops-ui";
import { useScope } from "@/components/scope-provider";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/page";
import { ChartSkeleton, MetricSkeletonGrid, StatusPill } from "@/components/ux";

type Summary = {
  totals: { currency: string; amount: number }[];
  recordCount: number;
};
type Resource = {
  resourceName: string;
  resourceType: string;
  estimatedMonthlyCost?: number;
  estimatedCostCurrency?: string;
  estimatedSavings?: number;
  savingsCurrency?: string;
};
type Recommendation = { estimatedSavings?: number; currency?: string };
type OnboardingStatus = {
  status: string;
  message?: string;
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

export default function Dashboard() {
  const { scope, subscriptions } = useScope();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<Summary>();
  const [resources, setResources] = useState<Resource[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [status, setStatus] = useState<OnboardingStatus>();

  useEffect(() => {
    if (!scope.tenantId) return;
    if (!scope.subscriptionId) {
      if (subscriptions.length === 0) setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([
      api<Summary>("/api/costs/summary", scope),
      api<Resource[]>("/api/resources", scope),
      api<Recommendation[]>("/api/recommendations", scope),
      api<OnboardingStatus>("/api/onboarding/status", scope),
    ])
      .then(([costs, resourceRows, recs, onboarding]) => {
        setSummary(costs);
        setResources(resourceRows);
        setRecommendations(recs);
        setStatus(onboarding);
      })
      .finally(() => setLoading(false));
  }, [scope, subscriptions.length]);

  const currency = summary?.totals[0]?.currency || "INR";
  const totalCost = summary?.totals.reduce((sum, row) => sum + row.amount, 0) || 0;
  const savings = recommendations.reduce((sum, row) => sum + (row.estimatedSavings ?? 0), 0);
  const latest = status?.subscriptions?.[0];
  const freshness = freshnessLabel(latest?.processing?.completedAt || latest?.collection?.completedAt, status?.status);
  const spendByResource = useMemo(
    () =>
      resources
        .map((row) => ({
          name: row.resourceName,
          cost: row.estimatedMonthlyCost || 0,
        }))
        .sort((a, b) => b.cost - a.cost)
        .slice(0, 6),
    [resources],
  );

  if (subscriptions.length === 0 && !loading) {
    return (
      <>
        <PageHeader title="Dashboard" description="Current subscription health and spend." />
        <Card className="flex flex-col items-center justify-center p-12 text-center shadow-sm">
          <h2 className="text-2xl font-bold tracking-tight">No subscriptions found</h2>
          <p className="mt-2 text-muted-foreground">Onboard Azure subscriptions before viewing cost data.</p>
          <a href="/onboarding" className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground">
            Start onboarding
          </a>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Dashboard" description="Executive Azure FinOps overview for the selected subscription." />

      {loading ? (
        <div className="space-y-6">
          <MetricSkeletonGrid />
          <ChartSkeleton message="Loading dashboard analytics..." />
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Metric title="Total cost" value={formatMoney(totalCost, currency)} caption={`${summary?.recordCount ?? 0} cost records analyzed`} />
            <Metric title="Estimated savings" value={formatMoney(savings, currency)} caption={`${recommendations.length} optimization findings`} />
            <Metric title="Resource count" value={resources.length.toString()} caption="Discovered resources with cost context" />
            <Metric title="Advisor findings" value={recommendations.length.toString()} caption="Savings and governance opportunities" />
          </div>

          <Card className="grid gap-5 p-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-lg font-semibold">Data freshness</h2>
                <StatusPill label={freshness.label} tone={freshness.tone} />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                Last updated: {formatDateTime(latest?.processing?.completedAt || latest?.collection?.completedAt)}
              </p>
              <div className="mt-5 grid gap-3 sm:grid-cols-4">
                {["Discovering Resources", "Collecting Cost Data", "Generating Recommendations", "Processing Analytics"].map((step, index) => (
                  <div key={step} className="rounded-xl border bg-background/40 p-3">
                    <div className="text-xs text-muted-foreground">Step {index + 1}</div>
                    <div className="mt-1 text-sm font-medium">{step}</div>
                    <div className="mt-3 h-2 rounded-full bg-muted">
                      <div className="h-2 rounded-full bg-primary" style={{ width: status?.status === "ready" ? "100%" : `${Math.min(80, (index + 1) * 20)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border bg-background/40 p-4">
              <h3 className="font-medium">Collection summary</h3>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <Info label="Collection" value={latest?.collection?.status || "Unknown"} />
                <Info label="Processing" value={latest?.processing?.status || "Unknown"} />
                <Info label="Records collected" value={String(latest?.collection?.recordsCollected ?? 0)} />
                <Info label="Cost facts" value={String(latest?.processing?.recordCounts?.costFacts ?? 0)} />
              </dl>
            </div>
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="p-5">
              <h2 className="font-semibold">Savings vs Spend</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={[{ name: "Current Spend", value: totalCost }, { name: "Potential Savings", value: savings }]}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                    <Bar dataKey="value" fill="#3b82f6" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card className="p-5">
              <h2 className="font-semibold">Top Costing Resources</h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={spendByResource}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                    <XAxis dataKey="name" hide />
                    <YAxis />
                    <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
                    <Area type="monotone" dataKey="cost" fill="#60a5fa" stroke="#3b82f6" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function Metric({ title, value, caption }: { title: string; value: string; caption: string }) {
  return (
    <Card className="p-5">
      <div className="text-sm text-muted-foreground">{title}</div>
      <div className="mt-3 text-2xl font-semibold">{value}</div>
      <div className="mt-2 text-xs text-muted-foreground">{caption}</div>
    </Card>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-medium capitalize">{value}</dd>
    </div>
  );
}
