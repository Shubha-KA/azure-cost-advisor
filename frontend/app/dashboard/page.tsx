"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/page";

type Summary = {
  totals: { currency: string; amount: number }[];
  recordCount: number;
};
type Resource = { estimatedSavings?: number; savingsCurrency?: string };

export default function Dashboard() {
  const { scope, subscriptions } = useScope();
  const [isInitializing, setIsInitializing] = useState(true);
  const [summary, setSummary] = useState<Summary>();
  const [resources, setResources] = useState<Resource[]>([]);
  const [recommendations, setRecommendations] = useState<unknown[]>([]);
  useEffect(() => {
    if (!scope.tenantId) return;
    if (!scope.subscriptionId) {
      // If we have a tenant but no subscriptions, we are done initializing the empty state
      if (subscriptions.length === 0) {
         setIsInitializing(false);
      }
      return;
    }
    Promise.all([
      api<Summary>("/api/costs/summary", scope),
      api<Resource[]>("/api/resources", scope),
      api<unknown[]>("/api/recommendations", scope),
    ]).then(([costs, resourceRows, recs]) => {
      setSummary(costs);
      setResources(resourceRows);
      setRecommendations(recs);
      setIsInitializing(false);
    }).catch(() => {
      setIsInitializing(false);
    });
  }, [scope, subscriptions.length]);
  const savings = resources.reduce(
    (sum, row) => sum + (row.estimatedSavings ?? 0),
    0,
  );
  const currency =
    resources.find((row) => row.savingsCurrency)?.savingsCurrency ||
    summary?.totals[0]?.currency ||
    "";
  const cards = [
    ["Total cost", summary?.totals.map((v) => `${v.currency} ${v.amount.toFixed(2)}`).join(" | ") || "No data"],
    ["Estimated savings", currency ? `${currency} ${savings.toFixed(2)}` : "No data"],
    ["Resource count", resources.length.toString()],
    ["Advisor findings", recommendations.length.toString()],
    ["Collection status", summary?.recordCount ? "Current" : "No current run"],
  ];
  return (
    <>
      <PageHeader title="Dashboard" description="Current subscription health and spend." />
      
      {isInitializing && !summary ? (
        <div className="flex h-48 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
        </div>
      ) : subscriptions.length === 0 ? (
        <Card className="flex flex-col items-center justify-center p-12 text-center shadow-sm">
          <h2 className="text-2xl font-bold tracking-tight">No Subscriptions Found</h2>
          <p className="mt-2 text-muted-foreground">
            You need to onboard Azure subscriptions before you can view cost data.
          </p>
          <a
            href="/onboarding"
            className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Start Onboarding
          </a>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {cards.map(([label, value]) => (
            <Card key={label} className="p-4">
              <div className="text-sm text-muted-foreground">{label}</div>
              <div className="mt-3 text-xl font-semibold">{value}</div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
