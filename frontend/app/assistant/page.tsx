"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";
import { PageHeader } from "@/components/page";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

type Message = { role: "user" | "assistant"; content: string };

const suggestions = [
  "Which resource costs me the most?",
  "How can I reduce my spend?",
  "Which resources are idle?",
  "Show AKS optimization opportunities.",
  "What are my top Azure costs?",
];

export default function Assistant() {
  const { scope } = useScope();
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setMessages((items) => [...items, { role: "user", content: question }]);
    setMessage("");
    setBusy(true);
    try {
      const result = await api<{ answer: string }>("/api/chat", scope, {
        method: "POST",
        body: JSON.stringify({ message: question }),
      });
      setMessages((items) => [...items, { role: "assistant", content: result.answer }]);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    ask(message);
  }

  return (
    <>
      <PageHeader title="AI assistant" description="Your Azure FinOps Copilot for cost, utilization, and optimization questions." />
      <div className="mx-auto max-w-4xl">
        <div className="mb-4 flex flex-wrap gap-2">
          {suggestions.map((item) => (
            <button
              key={item}
              onClick={() => ask(item)}
              className="rounded-full border bg-card px-3 py-2 text-sm text-muted-foreground transition hover:border-primary hover:text-foreground"
            >
              {item}
            </button>
          ))}
        </div>

        <Card className="mb-4 flex min-h-[520px] flex-col gap-4 p-5">
          {messages.length === 0 && (
            <div className="m-auto max-w-md text-center">
              <div className="text-2xl font-semibold">Ask FinsOpsIQ anything about your Azure spend</div>
              <p className="mt-3 text-sm text-muted-foreground">
                Try cost drivers, idle resources, AKS optimization, or savings recommendations.
              </p>
            </div>
          )}
          {messages.map((item, index) => (
            <div key={index} className={item.role === "user" ? "ml-auto max-w-2xl rounded-2xl bg-primary px-4 py-3 text-white" : "max-w-3xl rounded-2xl bg-muted/70 px-4 py-3"}>
              {item.role === "assistant" ? <AssistantAnswer content={item.content} /> : item.content}
            </div>
          ))}
          {busy && (
            <div className="max-w-sm rounded-2xl bg-muted/70 px-4 py-3 text-sm text-muted-foreground">
              <span>Analyzing Azure environment</span>
              <span className="ml-1 inline-flex w-8 justify-between align-middle">
                <span className="animate-bounce">●</span>
                <span className="animate-bounce [animation-delay:120ms]">●</span>
                <span className="animate-bounce [animation-delay:240ms]">●</span>
              </span>
            </div>
          )}
        </Card>

        <form onSubmit={submit} className="flex gap-2 rounded-2xl border bg-card p-2">
          <Input className="border-0 bg-transparent focus-visible:ring-0" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask a FinOps question..." />
          <Button disabled={busy}>{busy ? "Working..." : "Send"}</Button>
        </form>
      </div>
    </>
  );
}

function AssistantAnswer({ content }: { content: string }) {
  const cards = extractCards(content);
  return (
    <div className="space-y-4">
      {cards.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {cards.map((card, index) => (
            <div key={index} className="rounded-xl border bg-background/50 p-3">
              <div className="text-xs text-muted-foreground">{card.label}</div>
              <div className="mt-1 text-sm font-semibold">{card.value}</div>
            </div>
          ))}
        </div>
      )}
      <div className="whitespace-pre-wrap text-sm leading-6">{content}</div>
    </div>
  );
}

function extractCards(content: string) {
  const cards: { label: string; value: string }[] = [];
  const savings = content.match(/estimated savings[:\s-]+([₹A-Z]{0,4}\s?[\d,.]+(?:\/month)?)/i);
  const risk = content.match(/risk[:\s-]+([A-Za-z ]+)/i);
  const resource = content.match(/\b(?:resource|cluster)\s+\"?([A-Za-z0-9._-]+)\"?/i);
  const cost = content.match(/\b(?:cost|spend)\s+(?:is|of)?\s*([₹A-Z]{0,4}\s?[\d,.]+)/i);
  if (cost) cards.push({ label: "Cost", value: cost[1].trim() });
  if (savings) cards.push({ label: "Savings", value: savings[1].trim() });
  if (resource) cards.push({ label: "Resource", value: resource[1].trim() });
  if (risk) cards.push({ label: "Risk", value: risk[1].trim() });
  return cards.slice(0, 4);
}
