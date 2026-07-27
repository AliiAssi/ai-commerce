import type { Metadata } from "next";

import { Badge } from "@/components/ui/badge";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/panel";
import { listAudit } from "@/lib/api/admin";
import { requireToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Audit log · Admin" };

type RawParams = Record<string, string | string[] | undefined>;

export default async function AdminAuditPage(props: { searchParams: Promise<RawParams> }) {
  const raw = await props.searchParams;
  const value = Array.isArray(raw.page) ? raw.page[0] : raw.page;
  const parsed = Number.parseInt(value ?? "", 10);
  const page = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;

  // G4
  const result = await listAudit(await requireToken(), { page });

  return (
    <>
      <h1 className="mb-2 text-2xl font-bold">Audit log</h1>
      <p className="mb-6 text-sm text-ink-muted">
        Every admin action is recorded in the same transaction it happens in.
      </p>

      {result.items.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-card border border-border bg-surface shadow-card">
            <table className="w-full min-w-[42rem] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs tracking-wide text-ink-faint uppercase">
                  <th className="px-4 py-3 font-medium">When</th>
                  <th className="px-4 py-3 font-medium">Admin</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                  <th className="px-4 py-3 font-medium">Entity</th>
                  <th className="px-4 py-3 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.items.map((entry) => (
                  <tr key={entry.id}>
                    <td className="px-4 py-3 whitespace-nowrap text-ink-muted">
                      {formatDateTime(entry.created_at)}
                    </td>
                    <td className="px-4 py-3">{entry.admin_email}</td>
                    <td className="px-4 py-3">
                      <Badge variant="brand">{entry.action}</Badge>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">
                      {entry.entity_type}
                      {entry.entity_id ? ` #${entry.entity_id}` : ""}
                    </td>
                    <td className="max-w-[18rem] truncate px-4 py-3 text-xs text-ink-faint">
                      {entry.detail ? JSON.stringify(entry.detail) : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={result.page} pages={result.pages} baseUrl="/admin/audit" />
        </>
      ) : (
        <EmptyState
          title="Nothing recorded yet"
          body="Admin actions (product edits, stock changes, order transitions) will appear here."
        />
      )}
    </>
  );
}
