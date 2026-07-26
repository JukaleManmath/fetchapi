"use client";

import { useEffect, useState } from "react";
import { Terminal } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { getJobLogs, getSource } from "@/lib/api";
import type { JobLog } from "@/lib/types";

interface Props {
  params: { id: string };
}

const LEVEL_STYLES: Record<string, string> = {
  error: "text-red-400",
  warn: "text-yellow-400",
  warning: "text-yellow-400",
  info: "text-emerald-400",
  debug: "text-ink-3",
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toTimeString().slice(0, 8);
}

export default function LogsPage({ params }: Props) {
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    getSource(params.id)
      .then((source) => {
        if (!source.latest_job_id) {
          setEmpty(true);
          return;
        }
        return getJobLogs(source.latest_job_id).then((entries) => {
          if (entries.length === 0) {
            setEmpty(true);
          } else {
            setLogs(entries);
          }
        });
      })
      .catch(() => setEmpty(true));
  }, [params.id]);

  if (empty) {
    return (
      <EmptyState
        icon={<Terminal size={28} />}
        title="No ingestion logs yet"
        description="Logs appear here once ingestion has started for this source."
        className="mt-16"
      />
    );
  }

  if (logs.length === 0) {
    return null;
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-7 py-6">
        <p className="text-2xs font-mono text-ink-4 uppercase tracking-widest mb-4">
          {logs.length} log{logs.length !== 1 ? "s" : ""}
        </p>

        <div className="rounded-md border border-border-1 bg-surface-2 overflow-hidden">
          <table className="w-full font-mono text-xs">
            <tbody>
              {logs.map((log) => (
                <tr
                  key={log.id}
                  className="border-b border-border-1 last:border-0 hover:bg-canvas/30 transition-colors"
                >
                  <td className="py-1.5 px-3 text-ink-4 whitespace-nowrap w-20">
                    {formatTime(log.created_at)}
                  </td>
                  <td className="py-1.5 px-2 whitespace-nowrap w-16">
                    <span
                      className={`uppercase text-2xs font-semibold tracking-wider ${
                        LEVEL_STYLES[log.level] ?? "text-ink-3"
                      }`}
                    >
                      {log.level}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-ink-3 whitespace-nowrap w-28">
                    {log.stage ?? "—"}
                  </td>
                  <td className="py-1.5 px-3 text-ink break-all">
                    {log.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
