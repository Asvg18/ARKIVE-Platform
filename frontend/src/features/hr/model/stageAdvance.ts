/** When a move to the next stage asks "Are you sure?" first. The dialog
 *  that asks is AdvanceDialog; the move itself is useStageTransition. */

/** Whether advancing to `target` should be confirmed first — always,
 *  for any real stage. */
export function asksBeforeAdvancing(target: string | null): boolean {
  return target !== null;
}
