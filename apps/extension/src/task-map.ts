import type { AccessibleTaskMap, TaskMapItem } from "./contracts";

export interface SanitizedTaskMap {
  map: AccessibleTaskMap;
  invalidatedCount: number;
}

const isAuditableCompleted = (item: TaskMapItem): boolean =>
  item.status === "VERIFIED_COMPLETED" &&
  Boolean(item.verification_id) &&
  item.evidence.length > 0;

const isFreshSemanticItem = (item: TaskMapItem, version: number): boolean =>
  item.observation_version === version && Boolean(item.semantic_ref);

/** Reject stale or unauditable display claims even if an upstream producer is faulty. */
export const sanitizeTaskMap = (source: AccessibleTaskMap): SanitizedTaskMap => {
  let invalidatedCount = source.stale_invalidated_count;
  const completed = source.verified_completed.filter((item) => {
    const keep = isAuditableCompleted(item);
    if (!keep) invalidatedCount += 1;
    return keep;
  });
  const relevant = source.relevant_options.filter((item) => {
    const keep = item.status === "RELEVANT" && isFreshSemanticItem(item, source.observation_version);
    if (!keep) invalidatedCount += 1;
    return keep;
  });
  const next = source.next_action;
  const nextAction =
    next && next.status === "PLANNED" && isFreshSemanticItem(next, source.observation_version)
      ? next
      : null;
  if (next && !nextAction) invalidatedCount += 1;
  const uncertain = source.uncertain_items.filter((item) => item.status === "UNCERTAIN");
  return {
    map: {
      ...source,
      verified_completed: completed,
      relevant_options: relevant,
      next_action: nextAction,
      uncertain_items: uncertain,
      stale_invalidated_count: invalidatedCount
    },
    invalidatedCount
  };
};
