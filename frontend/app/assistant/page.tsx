"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

type Message = { role: "user" | "assistant"; content: string };

export default function Assistant() {
  const { scope } = useScope();
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;
    const question = message;
    setMessages((items) => [...items, { role: "user", content: question }]);
    setMessage(""); setBusy(true);
    try {
      const result = await api<{ answer: string }>("/api/chat", scope, {
        method: "POST", body: JSON.stringify({ message: question }),
      });
      setMessages((items) => [...items, { role: "assistant", content: result.answer }]);
    } finally { setBusy(false); }
  }
  return (
    <>
      <PageHeader title="AI assistant" description="Live inventory routes to Resource Graph; analysis routes to tenant-scoped AI context." />
      <Card className="mb-4 min-h-96 space-y-3">
        {messages.length === 0 && <p className="text-sm text-muted-foreground">Ask about current VMs, AKS, costs, trends, or recommendations.</p>}
        {messages.map((item, index) => <div key={index} className={item.role === "user" ? "ml-auto max-w-2xl rounded-xl bg-primary p-3 text-white" : "max-w-2xl whitespace-pre-wrap rounded-xl bg-muted p-3"}>{item.content}</div>)}
      </Card>
      <form onSubmit={submit} className="flex gap-2">
        <Input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask a FinOps question..." />
        <Button disabled={busy}>{busy ? "Working..." : "Send"}</Button>
      </form>
    </>
  );
}
