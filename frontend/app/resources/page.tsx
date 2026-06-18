"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { DataTable } from "@/components/data-table";
import { Button } from "@/components/ui/button";

type Resource = { resourceName: string; resourceType: string; resourceGroup: string; location: string; costBasis: string; sourceSystem: string };
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
  useEffect(() => {
    if (scope.subscriptionId) api<Resource[]>("/api/resources", scope).then(setRows);
  }, [scope]);
  async function loadLive(kind: string) {
    setActive(kind);
    setLive(await api<LiveResult>(`/api/inventory/${kind}`, scope));
  }
  return (
    <>
      <PageHeader title="Resource inventory" description="Resource Graph inventory with explicit cost provenance." />
      <div className="mb-5 flex flex-wrap gap-2">
        <Button className={active === "processed" ? "" : "bg-muted text-foreground"} onClick={() => setActive("processed")}>All analyzed</Button>
        {["resource-groups", "vms", "aks", "storage", "keyvaults"].map((kind) => (
          <Button key={kind} className={active === kind ? "" : "bg-muted text-foreground"} onClick={() => loadLive(kind)}>
            {kind.replace("-", " ")}
          </Button>
        ))}
      </div>
      {active === "processed" ? (
        <DataTable data={rows} columns={[
          { accessorKey: "resourceName", header: "Name" }, { accessorKey: "resourceType", header: "Type" },
          { accessorKey: "resourceGroup", header: "Resource group" }, { accessorKey: "location", header: "Location" },
          { accessorKey: "costBasis", header: "Cost basis" }, { accessorKey: "sourceSystem", header: "Source" },
        ]} />
      ) : (
        <>
          <p className="mb-3 text-sm text-muted-foreground">
            {live ? `${live.source} · ${live.result_count} results · ${live.timestamp}` : "Loading live Azure inventory..."}
          </p>
          <DataTable data={live?.records ?? []} columns={[
            { accessorKey: "name", header: "Name" }, { accessorKey: "type", header: "Type" },
            { accessorKey: "resourceGroup", header: "Resource group" }, { accessorKey: "location", header: "Location" },
          ]} />
        </>
      )}
    </>
  );
}
