/** Evidence export API helper (v2.3.4). */

import { createApiClient } from "@/lib/api/client";
import type { ConsoleSession } from "@/lib/auth/session";

export async function downloadEvidence(session: ConsoleSession, runId: string): Promise<Blob> {
  const client = createApiClient(session);
  return client.download(`/v2/evidence/${encodeURIComponent(runId)}`);
}
