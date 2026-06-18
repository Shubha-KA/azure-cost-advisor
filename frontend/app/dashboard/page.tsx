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
  const { scope } = useScope();
  const [summary, setSummary] = useState<Summary>();
  const [resources, setResources] = useState<Resource[]>([]);
  const [recommendations, setRecommendations] = useState<unknown[]>([]);
  useEffect(() => {
    if (!scope.subscriptionId) return;
    Promise.all([
      api<Summary>("/api/costs/summary", scope),
      api<Resource[]>("/api/resources", scope),
      api<unknown[]>("/api/recommendations", scope),
    ]).then(([costs, resourceRows, recs]) => {
      setSummary(costs);
      setResources(resourceRows);
      setRecommendations(recs);
    });
  }, [scope]);
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
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {cards.map(([label, value]) => (
          <Card key={label}>
            <div className="text-sm text-muted-foreground">{label}</div>
            <div className="mt-3 text-xl font-semibold">{value}</div>
          </Card>
        ))}
      </div>
    </>
  );
}
