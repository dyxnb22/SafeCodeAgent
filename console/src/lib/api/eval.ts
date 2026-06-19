/** Eval baseline read API helper (v2.3.4). */

import { createApiClient } from "@/lib/api/client";
import type { ConsoleSession } from "@/lib/auth/session";

export interface EvalBaselineSummary {
  suite: string;
  baseline_id: string;
}

export interface EvalBaselineListResponse {
  items: EvalBaselineSummary[];
}

export async function listEvalBaselines(session: ConsoleSession): Promise<EvalBaselineListResponse> {
  const client = createApiClient(session);
  return client.get<EvalBaselineListResponse>("/v2/eval/baselines");
}
