"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/finops-ui";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { DataTable } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TableSkeleton } from "@/components/ux";

type Resource = {
  resourceName: string;
  resourceType: string;
  resourceGroup: string;
  location: string;
  costBasis: string;
  sourceSystem: string;
  estimatedMonthlyCost?: number;
  estimatedCostCurrency?: string;
  wasteLevel?: string;
};
type LiveResult = {
  records: Array<Record<string, string>>;
  source: string;
  timestamp: string;
  result_count: number;
};

export default function Resources() {
  const { scope } = useScope();
  const [rows, setRows] = useState<Resource[]>([]);
  const [live, setLive] = useState<LiveResult>();
  const [active, setActive] = useState("processed");
  const [loading, setLoading] = useState(true);
  const [liveLoading, setLiveLoading] = useState(false);

  useEffect(() => {
    if (!scope.subscriptionId) return;
    setLoading(true);
    api<Resource[]>("/api/resources", scope)
      .then(setRows)
      .finally(() => setLoading(false));
  }, [scope]);

  async function loadLive(kind: string) {
    setActive(kind);
    setLiveLoading(true);
    try {
      setLive(await api<LiveResult>(`/api/inventory/${kind}`, scope));
    } finally {
      setLiveLoading(false);
    }
  }

  return (
    <>
      <PageHeader title="Resource inventory" description="Discovered Azure resources enriched with cost and waste context." />
      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <div className="text-sm text-muted-foreground">Resources discovered</div>
          <div className="mt-2 text-2xl font-semibold">{loading ? "—" : rows.length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-muted-foreground">Estimated monthly cost</div>
          <div className="mt-2 text-2xl font-semibold">
            {loading ? "—" : formatMoney(rows.reduce((sum, row) => sum + (row.estimatedMonthlyCost || 0), 0), rows[0]?.estimatedCostCurrency || "INR")}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-muted-foreground">Optimization candidates</div>
          <div className="mt-2 text-2xl font-semibold">{loading ? "—" : rows.filter((row) => row.wasteLevel && row.wasteLevel !== "NONE").length}</div>
        </Card>
      </div>
      <div className="mb-5 flex flex-wrap gap-2">
        <Button className={active === "processed" ? "" : "bg-muted text-foreground"} onClick={() => setActive("processed")}>All analyzed</Button>
        {["resource-groups", "vms", "aks", "storage", "keyvaults"].map((kind) => (
          <Button key={kind} className={active === kind ? "" : "bg-muted text-foreground"} onClick={() => loadLive(kind)}>
            {kind.replace("-", " ")}
          </Button>
        ))}
      </div>
      {active === "processed" ? (
        loading ? (
          <TableSkeleton rows={7} columns={6} />
        ) : (
          <DataTable data={rows} columns={[
            { accessorKey: "resourceName", header: "Name" },
            { accessorKey: "resourceType", header: "Type" },
            { accessorKey: "resourceGroup", header: "Resource group" },
            { accessorKey: "location", header: "Location" },
            {
              accessorKey: "estimatedMonthlyCost",
              header: "Monthly cost",
              cell: ({ row }) => formatMoney(row.original.estimatedMonthlyCost || 0, row.original.estimatedCostCurrency || "INR"),
            },
            { accessorKey: "wasteLevel", header: "Waste" },
          ]} />
        )
      ) : (
        <>
          <p className="mb-3 text-sm text-muted-foreground">
            {liveLoading ? "Loading live Azure inventory..." : live ? `${live.source} · ${live.result_count} results · ${live.timestamp}` : "Select a live inventory view."}
          </p>
          {liveLoading ? (
            <TableSkeleton rows={6} columns={4} />
          ) : (
            <DataTable data={live?.records ?? []} columns={[
              { accessorKey: "name", header: "Name" },
              { accessorKey: "type", header: "Type" },
              { accessorKey: "resourceGroup", header: "Resource group" },
              { accessorKey: "location", header: "Location" },
            ]} />
          )}
        </>
      )}
    </>
  );
}
