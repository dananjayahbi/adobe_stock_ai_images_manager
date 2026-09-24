/**
 * Behavioural verification of the research stream reducer's turn handling.
 *
 * The repo has no JavaScript test runner, so this transpiles the reducer with the
 * already-installed TypeScript compiler and asserts against the emitted JavaScript.
 * That gives real execution evidence without adding a framework the project does
 * not otherwise use — and it has already earned its place: it caught two real bugs
 * in this reducer that a type-check passed clean (an `error` turn being archived
 * twice, and a promoted buffer being re-archived by the next turn).
 *
 * Run from the repository root:
 *   npm --prefix frontend run verify:reducer
 */

const assert = require("node:assert/strict");
const path = require("node:path");

const {
  initialState,
  reduceEvent,
  orphanedTurn,
} = require(path.join(__dirname, "..", ".tmp-reducer", "researchStream.js"));

const ev = (type, payload = {}) => ({ type, ...payload });

let failures = 0;
function check(label, fn) {
  try {
    fn();
    console.log(`PASS  ${label}`);
  } catch (error) {
    failures += 1;
    console.log(`FAIL  ${label}`);
    console.log(`      ${error.message.split("\n")[0]}`);
  }
}

/** A turn that does work, then ends with a written answer. */
function turnWithAnswer() {
  let state = initialState();
  state = reduceEvent(state, ev("run_started", { mode: "research" }));
  state = reduceEvent(state, ev("thinking", { text: "Considering." }));
  state = reduceEvent(state, ev("tool_call", { name: "web_search", summary: "s", arguments: {} }));
  state = reduceEvent(state, ev("tool_result", { name: "web_search", summary: "done", ok: true }));
  state = reduceEvent(state, ev("message", { text: "The answer." }));
  state = reduceEvent(state, ev("run_finished", { status: "completed", answer: "The answer." }));
  return state;
}

check("a turn's thinking and steps are kept after it finishes", () => {
  const state = turnWithAnswer();
  assert.equal(state.turns.length, 1);
  assert.equal(state.turns[0].thinking, "Considering.");
  assert.equal(state.turns[0].steps.length, 1);
});

check("a turn with no assistant message is still recoverable", () => {
  // The reported defect: the run stops without writing an answer, so no assistant
  // message exists and the live block that was showing the reasoning disappears.
  let state = initialState();
  state = reduceEvent(state, ev("run_started", { mode: "research" }));
  state = reduceEvent(state, ev("thinking", { text: "Researching hard." }));
  state = reduceEvent(state, ev("tool_call", { name: "web_search", summary: "s", arguments: {} }));
  state = reduceEvent(state, ev("notice", { text: "Budget spent." }));
  state = reduceEvent(state, ev("run_finished", { status: "completed", answer: "" }));

  assert.equal(state.isStreaming, false);
  assert.equal(state.turns.length, 1, "the turn must be archived");
  // No assistant message exists for this turn, so it is orphaned.
  const orphan = orphanedTurn(state, 0);
  assert.ok(orphan, "the orphaned turn must be detectable");
  assert.equal(orphan.thinking, "Researching hard.");
  assert.equal(orphan.steps.length, 1);
});

check("the orphaned turn's activity is reachable after the run ends", () => {
  // Visibility for a message-less turn comes from `orphanedTurn`, not from
  // re-promoting the live buffers — a promoted buffer would be archived again by
  // the next turn's `run_started` and show one turn as two.
  let state = initialState();
  state = reduceEvent(state, ev("run_started", {}));
  state = reduceEvent(state, ev("thinking", { text: "Deep thought." }));
  state = reduceEvent(state, ev("run_finished", { status: "completed", answer: "" }));
  assert.equal(state.thinking, "", "the buffer is cleared, not promoted");
  const orphan = orphanedTurn(state, 0);
  assert.ok(orphan);
  assert.equal(orphan.thinking, "Deep thought.");
});

check("an error followed by run_finished does not double-count the turn", () => {
  // The backend's error path yields BOTH, so closing must be idempotent.
  let state = initialState();
  state = reduceEvent(state, ev("run_started", {}));
  state = reduceEvent(state, ev("thinking", { text: "Reasoning." }));
  state = reduceEvent(state, ev("error", { text: "boom" }));
  state = reduceEvent(state, ev("run_finished", { status: "error", answer: "" }));
  assert.equal(state.turns.length, 1, `expected 1 turn, got ${state.turns.length}`);
});

check("an errored turn's reasoning is still visible", () => {
  let state = initialState();
  state = reduceEvent(state, ev("run_started", {}));
  state = reduceEvent(state, ev("thinking", { text: "Reasoning." }));
  state = reduceEvent(state, ev("tool_call", { name: "web_search", summary: "s", arguments: {} }));
  state = reduceEvent(state, ev("error", { text: "boom" }));
  state = reduceEvent(state, ev("run_finished", { status: "error", answer: "" }));
  const orphan = orphanedTurn(state, 0);
  assert.ok(orphan, "the errored turn must be reachable");
  assert.equal(orphan.thinking, "Reasoning.");
  assert.equal(orphan.steps.length, 1);
});

check("a turn with no activity is not recorded", () => {
  let state = initialState();
  state = reduceEvent(state, ev("run_started", {}));
  state = reduceEvent(state, ev("run_finished", { status: "completed", answer: "x" }));
  assert.equal(state.turns.length, 0);
});

check("a second turn archives the first rather than replacing it", () => {
  let state = turnWithAnswer();
  state = reduceEvent(state, ev("run_started", {}));
  state = reduceEvent(state, ev("thinking", { text: "Second turn." }));
  state = reduceEvent(state, ev("run_finished", { status: "completed", answer: "Two." }));
  assert.equal(state.turns.length, 2);
  assert.equal(state.turns[0].thinking, "Considering.");
  assert.equal(state.turns[1].thinking, "Second turn.");
});

check("no orphan is reported while a turn is still streaming", () => {
  let state = initialState();
  state = reduceEvent(state, ev("run_started", {}));
  state = reduceEvent(state, ev("thinking", { text: "Working." }));
  assert.equal(orphanedTurn(state, 0), null);
});

check("a turn that produced a message is not orphaned", () => {
  const state = turnWithAnswer();
  assert.equal(orphanedTurn(state, 1), null, "an answered turn is not orphaned");
  assert.ok(orphanedTurn(state, 0), "but it is orphaned if no message exists");
});

console.log();
console.log("FAILURES:", failures);
process.exit(failures ? 1 : 0);
