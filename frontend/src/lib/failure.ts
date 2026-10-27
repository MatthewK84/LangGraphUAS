// What a failed planner request means for the operator: what happened, and
// what did not. The raw reason stays beside it for whoever debugs the stack.

export interface PlanFailure {
  readonly title: string;
  readonly detail: string;
  readonly raw: string;
}

type Step = "plan" | "ack";

const NOT_DONE: Readonly<Record<Step, string>> = {
  plan: "Nothing was computed or recorded.",
  ack: "The signature was not recorded.",
};

const BY_STATUS: Readonly<Record<string, { title: string; next: string }>> = {
  "400": {
    title: "Planner rejected these inputs",
    next: "Check the mission inputs, then analyze again.",
  },
  "401": {
    title: "Planner refused this browser's key",
    next: "Reload the page for a new session, or check the server's key.",
  },
  "403": {
    title: "Planner refused this browser's key",
    next: "Reload the page for a new session, or check the server's key.",
  },
  "422": {
    title: "Planner rejected these inputs",
    next: "Check the mission inputs, then analyze again.",
  },
  "429": {
    title: "Planner is rate limiting this browser",
    next: "Wait a minute, then try again.",
  },
};

const DOWN = {
  title: "Planner backend not answering",
  next: "Check that the backend is running, then try again.",
};

function status(raw: string): string | null {
  return /status (\d{3})$/.exec(raw)?.[1] ?? null;
}

/** A readable failure for a plan or ack request that did not complete. */
export function planFailure(step: Step, raw: string): PlanFailure {
  const code = status(raw);
  const known = code === null ? DOWN : (BY_STATUS[code] ?? DOWN);
  return {
    title: known.title,
    detail: `${NOT_DONE[step]} ${known.next}`,
    raw,
  };
}
