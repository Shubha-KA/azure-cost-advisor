"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { formatMoney, recommendationNarrative, recommendationTitle, riskFor } from "@/lib/finops-ui";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { Card } from "@/components/ui/card";
import { MetricSkeletonGrid, StatusPill } from "@/components/ux";

type Recommendation = {
  title: string;
  category: string;
  content: string;
  estimatedSavings: number;
  currency: string;
  sourceSystem: string;
  status: string;
  resourceId: string;
  evidence?: Record<string, unknown>;
};

export default function Recommendations() {
  const { scope } = useScope();
  const [rows, setRows] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!scope.subscriptionId) return;
    setLoading(true);
    api<Recommendation[]>("/api/recommendations", scope)
      .then(setRows)
      .finally(() => setLoading(false));
  }, [scope]);

  const currency = rows[0]?.currency || "INR";
  const totalSavings = rows.reduce((sum, row) => sum + (row.estimatedSavings || 0), 0);
  const highPriority = rows.filter((row) => (row.estimatedSavings || 0) > 300).length;
  const sorted = useMemo(() => [...rows].sort((a, b) => (b.estimatedSavings || 0) - (a.estimatedSavings || 0)), [rows]);

  return (
    <>
      <PageHeader title="Recommendations" description="Business-ready savings opportunities prioritized by impact and risk." />
      {loading ? (
        <div className="space-y-6">
          <MetricSkeletonGrid count={3} />
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="h-64 animate-pulse bg-muted" />
            <Card className="h-64 animate-pulse bg-muted" />
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
            <Card className="p-5">
              <div className="text-sm text-muted-foreground">Estimated monthly savings</div>
              <div className="mt-2 text-3xl font-semibold">{formatMoney(totalSavings, currency)}</div>
            </Card>
            <Card className="p-5">
              <div className="text-sm text-muted-foreground">Active recommendations</div>
              <div className="mt-2 text-3xl font-semibold">{rows.length}</div>
            </Card>
            <Card className="p-5">
              <div className="text-sm text-muted-foreground">High priority</div>
              <div className="mt-2 text-3xl font-semibold">{highPriority}</div>
            </Card>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            {sorted.map((row) => {
              const narrative = recommendationNarrative(row);
              const risk = riskFor(row.category, row.estimatedSavings);
              return (
                <Card key={row.resourceId + row.category} className="p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold">{recommendationTitle(row)}</h2>
                      <p className="mt-1 text-sm text-muted-foreground">{resourceName(row.resourceId)}</p>
                    </div>
                    <StatusPill label={`Risk: ${risk}`} tone={risk === "Low" ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500"} />
                  </div>

                  <div className="mt-5 grid gap-3 sm:grid-cols-3">
                    <Mini label="Estimated Savings" value={formatMoney(row.estimatedSavings, row.currency)} />
                    <Mini label="Status" value={row.status || "Active"} />
                    <Mini label="Source" value={row.sourceSystem || "FinsOpsIQ"} />
                  </div>

                  <div className="mt-5 space-y-4 text-sm">
                    <Section title="Why this was recommended" text={narrative.why} />
                    <Section title="Impact" text={narrative.impact} />
                    <Section title="Recommended action" text={narrative.action} />
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-background/40 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}

function Section({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <div className="font-medium">{title}</div>
      <p className="mt-1 text-muted-foreground">{text}</p>
    </div>
  );
}

function resourceName(resourceId: string) {
  const parts = resourceId.split("/").filter(Boolean);
  return parts[parts.length - 1] || "Azure resource";
}
