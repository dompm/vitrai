import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Konva from "konva";
import { App } from "../src/App";
import "../src/i18n";
import { makeInteractionProject } from "../src/editor/performance/fixtures";
import { saveToOPFS, loadProjectFromOPFS } from "../src/storage/opfs";
import { STORAGE_KEY } from "../src/components/Tutorial/types";
const query = new URLSearchParams(location.search);
const project = makeInteractionProject(
  Number(query.get("pieces") ?? 500),
  Number(query.get("vertices") ?? 96),
);
project.patternWidth = 1200;
project.patternHeight = 900;
project.patternScale = {
  pxPerUnit: 1,
  unit: "mm",
  line: { x1: 0, y1: 0, x2: 100, y2: 0 },
};
project.sheets[0] = {
  ...project.sheets[0],
  imageUrl: "/assets/orange.png",
  naturalWidth: 2816,
  naturalHeight: 1536,
  scale: project.patternScale,
};
await saveToOPFS(project, project.name);
localStorage.setItem("vitraux-last-project", project.name);
localStorage.setItem(STORAGE_KEY, JSON.stringify({ completed: true }));
const root = createRoot(document.getElementById("root")!);
root.render(
  query.has("strict") ? (
    <StrictMode>
      <App />
    </StrictMode>
  ) : (
    <App />
  ),
);
const frame = () =>
  new Promise<number>((resolve) => requestAnimationFrame(resolve));
const settle = async () => {
  for (let i = 0; i < 8; i++) await frame();
};
const output = document.getElementById("results")!;
const assert = (test: unknown, message: string) => {
  if (!test) throw new Error(message);
};
const stages = () => ({ pattern: Konva.stages[0], glass: Konva.stages[1] });
const outlineFor = (id: string) =>
  stages()
    .glass.find(".sheet-outline")
    .find((node) => node.id() === id)!;
const transform = (node: Konva.Node) => ({
  x: node.x(),
  y: node.y(),
  rotation: node.rotation(),
  scale: node.scaleX(),
});
const equal = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);
async function select(index = 0, multi = false) {
  const node = stages().glass.find(".sheet-outline")[index];
  assert(node, "Missing fixture outline");
  const id = node.id();
  node.fire("click", { evt: { shiftKey: multi } }, true);
  await settle();
  return outlineFor(id);
}
function download(value: unknown, name: string) {
  const a = document.createElement("a");
  a.textContent = "Download results";
  a.download = name;
  a.href = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  output.after(a);
}
async function measure() {
  const target = await select();
  const original = transform(target);
  const counts: Record<string, number> = {};
  let work = 0;
  const draw = Konva.Layer.prototype.drawScene,
    hit = Konva.Layer.prototype.drawHit;
  Konva.Layer.prototype.drawScene = function (...args) {
    const key = `${this.getStage() === stages().pattern ? "pattern" : "glass"}.${this.index}`;
    counts[key] = (counts[key] ?? 0) + 1;
    const start = performance.now();
    try {
      return draw.apply(this, args);
    } finally {
      work += performance.now() - start;
    }
  };
  Konva.Layer.prototype.drawHit = function (...args) {
    const start = performance.now();
    try {
      return hit.apply(this, args);
    } finally {
      work += performance.now() - start;
    }
  };
  const intervals: number[] = [],
    canvas: number[] = [];
  let last = await frame(),
    start = last,
    events = 0;
  target.fire("dragstart", { target, evt: { ctrlKey: true } });
  try {
    while (performance.now() - start < 5000) {
      const now = await frame();
      intervals.push(now - last);
      last = now;
      canvas.push(work);
      work = 0;
      for (let i = 0; i < 2; i++) {
        target.position({ x: original.x + (events % 100), y: original.y + 10 });
        target.fire("dragmove", {
          target,
          evt: { ctrlKey: query.get("snap") !== "1" },
        });
        events++;
      }
    }
    target.fire("dragend", { target, evt: { ctrlKey: true } });
    await settle();
  } finally {
    Konva.Layer.prototype.drawScene = draw;
    Konva.Layer.prototype.drawHit = hit;
  }
  const p95 = (values: number[]) =>
    [...values].sort((a, b) => a - b)[Math.floor((values.length - 1) * 0.95)];
  const result = {
    pieces: project.pieces.length,
    vertices: project.pieces[0].polygon.length,
    snap: query.get("snap") === "1",
    events,
    frameP95: p95(intervals),
    canvasWorkP95: p95(canvas),
    framesOver50ms: intervals.filter((n) => n > 50).length,
    draws: counts,
  };
  output.textContent = JSON.stringify(result, null, 2);
  download(
    result,
    `main-drag-${project.pieces.length}-${project.pieces[0].polygon.length}.json`,
  );
}
async function behavior() {
  const checks: string[] = [];
  const { pattern, glass } = stages();
  const order = () => pattern.find(".pattern-piece").map((node) => node.id());
  const beforeOrder = order();
  let target = await select();
  const id = target.id();
  const start = transform(target);
  const image = pattern
    .find(".pattern-piece")
    .find((node) => node.id() === id)
    ?.findOne("Image")
    ?.getAttr("image");
  assert(image, "Texture must be loaded");
  assert(
    equal(order(), beforeOrder),
    "Selection must preserve Pattern paint order",
  );
  target.fire("dragstart", { target, evt: {} });
  target.position({ x: start.x + 57, y: start.y + 33 });
  target.fire("dragmove", { target, evt: { ctrlKey: true } });
  await settle();
  target.position({ x: start.x + 73, y: start.y + 41 });
  target.fire("dragend", { target, evt: {} });
  await settle();
  const final = transform(target);
  assert(
    final.x === start.x + 73 && final.y === start.y + 41,
    "Exact final drag value",
  );
  const fill = glass.find(".sheet-fill").find((node) => node.id() === id)!;
  assert(fill.x() === final.x && fill.y() === final.y, "Fill follows outline");
  const texture = pattern
    .find(".pattern-piece")
    .find((node) => node.id() === id)
    ?.findOne("Image");
  assert(
    texture?.x() === -final.x && texture?.y() === -final.y,
    "Pattern texture follows drag",
  );
  checks.push("exact drag, clipped fill and mirrored texture");
  const undo = document.querySelector<HTMLButtonElement>(
      'button[title*="Ctrl+Z"]',
    )!,
    redo = document.querySelector<HTMLButtonElement>(
      'button[title*="Ctrl+Y"]',
    )!;
  undo.click();
  await settle();
  assert(equal(transform(outlineFor(id)), start), "One Undo restores start");
  redo.click();
  await settle();
  assert(equal(transform(outlineFor(id)), final), "One Redo restores end");
  checks.push("one-step undo and redo");
  const secondId = glass
    .find(".sheet-outline")
    .find((node) => node.id() !== id)!
    .id();
  outlineFor(secondId).fire("click", { evt: { shiftKey: true } }, true);
  await settle();
  assert(equal(order(), beforeOrder), "Multi-selection must preserve order");
  assert(
    pattern
      .find(".pattern-piece")
      .find((node) => node.id() === id)
      ?.findOne("Image")
      ?.getAttr("image") === image,
    "Selection must reuse loaded image",
  );
  const secondStart = transform(outlineFor(secondId));
  target = outlineFor(id);
  target.fire("dragstart", { target, evt: {} });
  target.position({ x: final.x + 13, y: final.y + 17 });
  target.fire("dragmove", { target, evt: { ctrlKey: true } });
  await settle();
  target.fire("dragend", { target, evt: {} });
  await settle();
  const secondEnd = transform(outlineFor(secondId));
  assert(
    secondEnd.x === secondStart.x + 13 && secondEnd.y === secondStart.y + 17,
    "Main group movement must remain intact",
  );
  checks.push(
    "group movement, paint order and shared texture survive layer repartition",
  );
  undo.click();
  await settle();
  assert(
    equal(transform(outlineFor(secondId)), secondStart),
    "Group movement undoes once",
  );
  target = await select();
  const rotationStart = transform(target);
  const handle = glass
    .find(".sheet-handle")
    .find((node) => node.id() === target.id())!
    .findOne("Circle")!;
  handle.fire(
    "pointerdown",
    { target: handle, evt: { target: glass.content } },
    true,
  );
  await settle();
  const turnPoint = target.getAbsoluteTransform().point({ x: 100, y: 0 });
  const glassRect = glass.container().getBoundingClientRect();
  glass.setPointersPositions({
    clientX: glassRect.left + turnPoint.x,
    clientY: glassRect.top + turnPoint.y,
  });
  glass.fire("pointermove", { evt: { shiftKey: false } });
  glass.fire("pointerup", { evt: {} });
  await settle();
  assert(
    Math.abs(outlineFor(target.id()).rotation() - 90) < 1e-6,
    "Immediate rotation release must retain the exact final angle",
  );
  undo.click();
  await settle();
  assert(
    equal(transform(outlineFor(target.id())), rotationStart),
    "Rotation undoes once",
  );
  checks.push(
    "rotation callback and rapid release retain exact value with one-step undo",
  );
  const well = pattern.container().closest(".canvas-well")!;
  const groups = pattern
    .getLayers()
    .flatMap((layer) =>
      layer.getChildren().filter((node) => node.getClassName() === "Group"),
    );
  const anchor = { x: 100, y: 100 },
    rect = well.getBoundingClientRect();
  const wheel = new WheelEvent("wheel", {
    ctrlKey: true,
    deltaY: -50,
    clientX: rect.left + anchor.x,
    clientY: rect.top + anchor.y,
    bubbles: true,
    cancelable: true,
  });
  const point = { x: wheel.clientX - rect.left, y: wheel.clientY - rect.top };
  const imagePoint = groups[0]
    .getAbsoluteTransform()
    .copy()
    .invert()
    .point(point);
  well.dispatchEvent(wheel);
  await settle();
  for (const group of groups) {
    const actual = group.getAbsoluteTransform().point(imagePoint);
    assert(
      Math.hypot(actual.x - point.x, actual.y - point.y) < 1e-6,
      "Zoom anchors every drawing layer",
    );
  }
  checks.push("viewport zoom across drawing surfaces");
  await new Promise((resolve) => setTimeout(resolve, 700));
  const saved = await loadProjectFromOPFS(project.name);
  assert(
    saved?.pieces.length === project.pieces.length,
    "Persisted project retains pieces",
  );
  checks.push("OPFS persistence");
  output.textContent = JSON.stringify({ checks }, null, 2);
}
document.getElementById("run")!.onclick = () =>
  measure().catch((error) => {
    output.textContent = String(error);
  });
document.getElementById("behavior")!.onclick = () =>
  behavior().catch((error) => {
    output.textContent = String(error);
  });
const native = document.createElement("button");
native.textContent = "Prepare native drag";
document.getElementById("bench")!.prepend(native);
native.onclick = async () => {
  const target = await select();
  const point = target.getAbsoluteTransform().point({ x: 0, y: 0 });
  const rect = stages().glass.container().getBoundingClientRect();
  output.textContent = JSON.stringify(
    {
      nativeDrag: {
        id: target.id(),
        original: transform(target),
        from: { x: point.x + rect.left, y: point.y + rect.top },
        to: { x: point.x + rect.left + 60, y: point.y + rect.top + 30 },
      },
    },
    null,
    2,
  );
};
