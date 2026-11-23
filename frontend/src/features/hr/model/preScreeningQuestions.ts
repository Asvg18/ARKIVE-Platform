import type { PreScreeningQuestion } from "../../../shared/api/pipeline";

let nextId = 0;
export function makeQuestion(): PreScreeningQuestion {
  nextId += 1;
  return { id: `q-${Date.now()}-${nextId}`, text: "", required: true };
}
