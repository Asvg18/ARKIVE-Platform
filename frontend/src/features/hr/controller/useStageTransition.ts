import { useState } from "react";
import { useAuth } from "../../auth/controller/AuthContext";
import { apiFetch, ApiError } from "../../../shared/api/client";
import type { StageType, TransitionResponse } from "../../../shared/api/pipeline";
import { stageGateRefusal, type StageGateRefusal } from "../../../shared/lib/stageGate";

/**
 * Moving a candidate to another stage, the way HR does it from the
 * Candidate Profile's Advance button and from the HR Workflow page (the
 * list's Advance, or a card dropped on the board). Both pages used to
 * write this exchange out for themselves:
 *
 *   1. "Are you sure?" (AdvanceDialog) before a move to the next stage;
 *   2. the transition request, which the server's DFA allows or refuses;
 *   3. if the stage being left recorded nothing, the refusal is a question
 *      (StageAdvanceDialog): with a reason, the same request is sent again
 *      as an acknowledged skip.
 *
 * Nothing here decides whether a move is legal; the server does. Each page
 * still decides when to ask first and where a refusal is shown.
 */

/** One move. Pages add what they need to show it, such as the candidate. */
export interface StageMove {
  applicationId: number | string;
  target: StageType;
}

export function useStageTransition<M extends StageMove>(onMoved: () => void) {
  const { token } = useAuth();
  // A move waiting on "Are you sure?". Held before any request is sent.
  const [confirming, setConfirming] = useState<M | null>(null);
  const [movingId, setMovingId] = useState<M["applicationId"] | null>(null);
  // The sufficiency gate's 409, held until HR answers it. The move is
  // remembered whole, so confirming replays exactly the request that was
  // refused, alongside the server's own list of what is outstanding.
  const [pendingSkip, setPendingSkip] = useState<(M & StageGateRefusal) | null>(null);
  const [skipSubmitting, setSkipSubmitting] = useState(false);
  const [skipError, setSkipError] = useState<string | null>(null);

  async function requestTransition(move: StageMove, override?: { reason: string }) {
    await apiFetch<TransitionResponse>(`/applications/${move.applicationId}/transition`, {
      method: "POST",
      token,
      body: {
        target_stage: move.target,
        ...(override ? { acknowledged_incomplete: true, reason: override.reason } : {}),
      },
    });
  }

  /** Sends `move`. The gate's refusal opens the skip question instead of
   *  failing; any other refusal goes to `onError`, in the server's words
   *  or else `fallback`. */
  async function send(move: M, fallback: string, onError: (message: string) => void) {
    setMovingId(move.applicationId);
    try {
      await requestTransition(move);
      onMoved();
    } catch (err) {
      const gate = stageGateRefusal(err);
      if (gate) {
        setSkipError(null);
        setPendingSkip({ ...move, ...gate });
        return;
      }
      onError(err instanceof ApiError ? err.message : fallback);
    } finally {
      setMovingId(null);
    }
  }

  async function confirmSkip(reason: string) {
    if (!pendingSkip) return;
    setSkipSubmitting(true);
    setSkipError(null);
    try {
      await requestTransition(pendingSkip, { reason });
      setPendingSkip(null);
      onMoved();
    } catch (err) {
      setSkipError(err instanceof ApiError ? err.message : "That move was rejected.");
    } finally {
      setSkipSubmitting(false);
    }
  }

  function cancelSkip() {
    setPendingSkip(null);
    setSkipError(null);
  }

  /** Closes "Are you sure?" and hands back the move it was asking about. */
  function takeConfirming(): M | null {
    const move = confirming;
    setConfirming(null);
    return move;
  }

  return {
    confirming,
    askFirst: (move: M) => setConfirming(move),
    cancelConfirming: () => setConfirming(null),
    takeConfirming,
    movingId,
    send,
    pendingSkip,
    skipSubmitting,
    skipError,
    confirmSkip,
    cancelSkip,
  };
}
