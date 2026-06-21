"use client";

import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/page";
import { DataTable } from "@/components/data-table";

type CostRow = { date?: string; period?: string; service_name?: string; resource_group?: string; currency: string; costAmount: number };

export default function Costs() {
  const { scope } = useScope();
  const [trends, setTrends] = useState<CostRow[]>([]);
  const [services, setServices] = useState<CostRow[]>([]);
  const [groups, setGroups] = useState<CostRow[]>([]);
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    setIsMounted(true);
    if (!scope.subscriptionId) return;
    Promise.all([
      api<CostRow[]>("/api/costs/trends", scope),
      api<CostRow[]>("/api/costs/services", scope),
      api<CostRow[]>("/api/costs/resource-groups", scope),
    ]).then(([a, b, c]) => { setTrends(a); setServices(b); setGroups(c); });
  }, [scope]);
  return (
    <>
      <PageHeader title="Cost analytics" description="Currency-safe actual Azure Cost Management facts." />
      <Card className="mb-6 h-80 min-w-0">
        {isMounted && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trends}>
              <XAxis dataKey="date" /><YAxis /><Tooltip />
              <Line type="monotone" dataKey="costAmount" stroke="#3b82f6" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card><h2 className="mb-4 font-semibold">Service breakdown</h2><DataTable data={services} columns={[
          { accessorKey: "service_name", header: "Service" }, { accessorKey: "currency", header: "Currency" }, { accessorKey: "costAmount", header: "Actual cost" },
        ]} /></Card>
        <Card><h2 className="mb-4 font-semibold">Resource group breakdown</h2><DataTable data={groups} columns={[
          { accessorKey: "resource_group", header: "Resource group" }, { accessorKey: "currency", header: "Currency" }, { accessorKey: "costAmount", header: "Actual cost" },
        ]} /></Card>
      </div>
    </>
  );
}
