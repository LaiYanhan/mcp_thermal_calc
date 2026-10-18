/* 编辑器只维护图形与交互，工程数值全部来自后端会话。 */
"use strict";

const clone = value => JSON.parse(JSON.stringify(value));
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
const sameUnit = (a, b) => {
  const aliases = {MWt: "MW", MWe: "MW", MWht: "MWh", "°C": "℃", "kJ/(kg·K)": "kJ/(kg·℃)", "1": "/"};
  return (aliases[a] || a) === (aliases[b] || b);
};

// 在卡片边界外建立正交网格，A* 寻路；无法连通时不绘制穿过卡片的假连线。
function routeWire(start, end, obstacles) {
  const xs = [...new Set([start.x, end.x, ...obstacles.flatMap(r => [r.left, r.right])])].sort((a, b) => a - b);
  const ys = [...new Set([start.y, end.y, ...obstacles.flatMap(r => [r.top, r.bottom])])].sort((a, b) => a - b);
  const width = xs.length;
  const point = id => ({x: xs[id % width], y: ys[Math.floor(id / width)]});
  const blocked = (a, b) => obstacles.some(r => a.x === b.x
    ? a.x > r.left && a.x < r.right && Math.max(a.y, b.y) > r.top && Math.min(a.y, b.y) < r.bottom
    : a.y > r.top && a.y < r.bottom && Math.max(a.x, b.x) > r.left && Math.min(a.x, b.x) < r.right);
  const source = ys.indexOf(start.y) * width + xs.indexOf(start.x);
  const target = ys.indexOf(end.y) * width + xs.indexOf(end.x);
  const distance = new Map([[source, 0]]), previous = new Map(), heap = [];
  const heuristic = p => Math.abs(p.x - end.x) + Math.abs(p.y - end.y);
  const push = item => {
    let i = heap.length;
    heap.push(item);
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (heap[parent].score <= item.score) break;
      heap[i] = heap[parent]; i = parent;
    }
    heap[i] = item;
  };
  const pop = () => {
    const first = heap[0], last = heap.pop();
    if (heap.length) {
      let i = 0;
      while (2 * i + 1 < heap.length) {
        let child = 2 * i + 1;
        if (child + 1 < heap.length && heap[child + 1].score < heap[child].score) child++;
        if (heap[child].score >= last.score) break;
        heap[i] = heap[child]; i = child;
      }
      heap[i] = last;
    }
    return first;
  };
  push({id: source, cost: 0, score: heuristic(start)});
  while (heap.length) {
    const current = pop();
    if (current.cost !== distance.get(current.id)) continue;
    if (current.id === target) {
      const path = [end];
      let id = target;
      while (id !== source) { id = previous.get(id); path.push(point(id)); }
      path.reverse();
      return path.filter((p, i) => i === 0 || i === path.length - 1 ||
        !((path[i - 1].x === p.x && p.x === path[i + 1].x) || (path[i - 1].y === p.y && p.y === path[i + 1].y)));
    }
    const a = point(current.id), x = current.id % width, y = Math.floor(current.id / width);
    const neighbors = [];
    if (x > 0) neighbors.push(current.id - 1);
    if (x + 1 < width) neighbors.push(current.id + 1);
    if (y > 0) neighbors.push(current.id - width);
    if (y + 1 < ys.length) neighbors.push(current.id + width);
    for (const id of neighbors) {
      const b = point(id);
      if (blocked(a, b)) continue;
      const cost = current.cost + Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
      if (cost >= (distance.get(id) ?? Infinity)) continue;
      distance.set(id, cost); previous.set(id, current.id);
      push({id, cost, score: cost + heuristic(b)});
    }
  }
  return [];
}

function effectivePins(formula, step) {
  const target = step.solve_target || formula.default_target;
  if (!target || !formula.solve_targets?.includes(target)) return {inputs: formula.inputs, outputs: formula.outputs};
  return {inputs: formula.variables.filter(pin => pin.name !== target), outputs: formula.variables.filter(pin => pin.name === target)};
}

function configureTarget(original, stepId, formula, target) {
  const pipeline = clone(original), step = pipeline.steps.find(item => item.step_id === stepId);
  if (!formula.solve_targets.includes(target)) throw new Error("该参数不能作为待求量");
  const previous = step.solve_target || formula.default_target;
  if (previous === target) return pipeline;
  const pins = Object.fromEntries(formula.variables.map(pin => [pin.name, pin]));
  const previousOutput = step.output_map[previous], source = step.input_map[target];
  const remaining = Object.fromEntries(Object.entries(step.input_map).filter(([name]) => name !== target));
  const input = pipeline.required_inputs.find(pin => pin.name === source);
  // 原外部输入可直接改由当前节点产出，下游保持原有变量引用。
  const reuse = input && !Object.values(remaining).includes(source);
  if (reuse) {
    pipeline.required_inputs = pipeline.required_inputs.filter(pin => pin.name !== source);
    delete pipeline.layout?.[`input:${source}`];
  }
  const used = new Set([...pipeline.required_inputs.map(pin => pin.name), ...pipeline.steps.flatMap(item => Object.values(item.output_map))]);
  let output = reuse ? source : target, suffix = 2;
  if (!reuse) while (used.has(output)) output = `${target}_${suffix++}`;
  pipeline.required_inputs.push({...pins[previous], name: previousOutput, default_value: null, kind: "input"});
  step.solve_target = target;
  step.input_map = {...remaining, [previous]: previousOutput};
  step.output_map = {[target]: output};
  return pipeline;
}

function makeStep(pipeline, formula, variables, anchorId, mode) {
  const anchor = pipeline.steps.find(step => step.step_id === anchorId);
  const used = new Set(Object.keys(variables));
  const unique = (base, occupied) => { let name = base, index = 2; while (occupied.has(name)) name = `${base}_${index++}`; occupied.add(name); return name; };
  const step = {step_id: unique(formula.id.replace(/\./g, "_"), new Set(pipeline.steps.map(s => s.step_id))), formula_id: formula.id, description: "", input_map: {}, output_map: {}};
  if (mode === "replace" && anchor?.formula_id === formula.id) step.solve_target = anchor.solve_target;
  const pins = effectivePins(formula, step);
  for (const pin of pins.inputs) {
    const old = mode === "replace" && anchor?.input_map[pin.name];
    step.input_map[pin.name] = old && sameUnit(variables[old]?.unit, pin.unit) ? old :
      (variables[pin.name] && sameUnit(variables[pin.name].unit, pin.unit) && !Object.values(anchor?.output_map || {}).includes(pin.name) ? pin.name : "");
  }
  const retained = new Set();
  for (const pin of pins.outputs) {
    const old = mode === "replace" && Object.entries(anchor?.output_map || {}).find(([name, variable]) =>
      !retained.has(variable) && sameUnit(variables[variable]?.unit, pin.unit) && (name === pin.name || pins.outputs.length === 1));
    step.output_map[pin.name] = old ? old[1] : unique(pin.name, used);
    if (old) retained.add(old[1]);
  }
  return step;
}

let sessionView, selectedStepId = null, drawerPipeline = null, activeStage = 1;
let insertionMode = "after", insertionAnchor = null, panX = 0, panY = 0, busy = false;
let mutationQueue = Promise.resolve(), wireFrame = null, drag = null, highlightedNode = null;
let pendingParameters = {};
let debugMode = false, debugStageInitialized = false;
const $ = id => document.getElementById(id);
const urlParams = typeof location === "undefined" ? new URLSearchParams() : new URLSearchParams(location.search);
const sessionId = urlParams.get("session_id") || "default";
const queryParams = new URLSearchParams();
for (const key of ["pipeline", "pipeline_id", "scenario_id", "reset"]) {
  if (urlParams.has(key)) queryParams.set(key, urlParams.get(key));
}
const sessionUrl = `/api/session/${encodeURIComponent(sessionId)}`;
let initialSessionLoad = true;
const formulaById = id => sessionView.formulas.find(formula => formula.id === id);
const needsScenario = () => ["INITIAL", "SCENARIO_PROPOSED"].includes(sessionView.current_state) ||
  (sessionView.current_state === "MODIFICATION_REQUESTED" && !Object.keys(sessionView.inspected_parameters).length);

async function api(url, body) {
  const response = await fetch(url, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
  return data;
}

function showMessage(message = "") {
  $("editor-message").textContent = message;
  $("editor-message").classList.toggle("hidden", !message);
}

function enqueue(action) {
  mutationQueue = mutationQueue.then(async () => {
    busy = true; $("btn-main-action").disabled = true;
    try { showMessage(); await action(); }
    catch (error) {
      try { await syncFromBackend(); } catch (_) { /* 保留原错误，不能把本地状态当成已保存。 */ }
      showMessage(error.message);
    } finally { busy = false; $("btn-main-action").disabled = false; }
  });
  return mutationQueue;
}

async function syncFromBackend() {
  const query = initialSessionLoad && queryParams.toString();
  const nextView = await api(sessionUrl + (query ? `?${query}` : ""));
  const changed = JSON.stringify(nextView) !== JSON.stringify(sessionView);
  sessionView = nextView;
  debugMode = sessionView.editor_debug === true;
  initialSessionLoad = false;
  if (query && queryParams.has("reset") && typeof history !== "undefined") {
    const url = new URL(location.href);
    url.searchParams.delete("reset");
    history.replaceState(null, "", url);
  }
  const previousStage = activeStage;
  if (debugMode) {
    if (!debugStageInitialized) {
      activeStage = urlParams.get("stage") === "2" ? 2 : 1;
      debugStageInitialized = true;
    }
  } else {
    activeStage = sessionView.editor_stage === 2 ? 2 : 1;
  }
  if (changed || previousStage !== activeStage) renderGraph();
  const errors = sessionView.validation?.errors || [];
  showMessage(errors.map(item => item.message).join("；"));
}

async function savePipeline(pipeline) {
  await api(sessionUrl + "/pipeline", {pipeline, allow_incomplete: true});
  const allowed = new Set(pipeline.required_inputs.map(pin => pin.name));
  pendingParameters = Object.fromEntries(Object.entries(pendingParameters).filter(([name]) => allowed.has(name)));
  await syncFromBackend();
}

function switchStage(stage) {
  if (!debugMode) return;
  if (!sessionView || (stage === 2 && needsScenario())) return;
  if (Object.keys(pendingParameters).length) {
    const parameters = takePendingParameters();
    enqueue(async () => { await api(sessionUrl + "/parameters", {parameters}); activeStage = stage; await syncFromBackend(); });
    return;
  }
  activeStage = stage; renderGraph();
}

function takePendingParameters() {
  const parameters = pendingParameters; pendingParameters = {};
  return parameters;
}

function handlePrimaryAction() {
  if (!debugMode) return;
  const parameters = takePendingParameters();
  return enqueue(async () => {
    if (needsScenario()) {
      await api(sessionUrl + "/confirm_scenario", {confirmed: true});
      await api(sessionUrl + "/parameters", {parameters});
      activeStage = 2;
    } else if (activeStage === 1) {
      activeStage = 2;
    } else {
      const inspection = await api(sessionUrl + "/parameters", {parameters});
      if (!inspection.is_complete) throw new Error("请补齐参数：" + inspection.missing_inputs.map(p => p.description).join("、"));
      await api(sessionUrl + "/confirm_parameters", {confirmed: true});
      await api(sessionUrl + "/calculate", {});
    }
    await syncFromBackend();
  });
}

const formatValue = value => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("zh-CN", {maximumFractionDigits: 4, useGrouping: false}) : "—";
function pinRow(pin, variable, direction, value) {
  return `<div class="flex justify-between items-center gap-2 py-0.5 relative group" data-${direction}="${escapeHtml(variable)}">
    <span class="text-slate-600 break-words text-[11px]">${escapeHtml(pin?.description || variable)}</span>
    <span class="font-mono text-right shrink-0 text-xs ${direction === 'out' ? 'text-softPin-outText font-black' : 'text-slate-800'}">
      <b data-value="${escapeHtml(variable)}">${formatValue(value)}</b> <small class="text-slate-400 font-normal">${escapeHtml(pin?.unit)}</small>
    </span></div>`;
}

function renderConstantCard(pin, value, canEdit, extra = "") {
  return `<section data-node="input:${escapeHtml(pin.name)}" class="flow-node-box node-constant absolute p-1.5 ${extra}">
    <div class="flex items-center justify-between pb-0.5 mb-1 border-b border-amber-200/60">
      <span class="text-[11px] font-black text-softPin-constText truncate" title="${escapeHtml(pin.description)}">${escapeHtml(pin.description)}</span>
      <span class="w-1.5 h-1.5 rounded-full bg-softPin-constDot shrink-0"></span>
    </div>
    <div data-out="${escapeHtml(pin.name)}" class="flex items-center gap-1 font-mono">
      <input data-parameter="${escapeHtml(pin.name)}" aria-label="${escapeHtml(pin.description)}" type="number" step="any" value="${escapeHtml(value)}" ${canEdit ? "" : "disabled"} class="w-full min-w-0 px-1 py-0.5 text-right border border-softPin-constBorder rounded text-xs bg-white text-softPin-constText font-black disabled:bg-amber-50/50 focus:outline-none focus:ring-1 focus:ring-amber-400">
      <span class="shrink-0 text-[10px] text-amber-900 font-bold">${escapeHtml(pin.unit)}</span>
    </div>
  </section>`;
}

function renderInputCard(pin, value, canEdit, extra = "") {
  return `<section data-node="input:${escapeHtml(pin.name)}" class="flow-node-box node-input absolute p-1.5 ${extra}">
    <div class="flex items-center justify-between pb-0.5 mb-1 border-b border-green-200/60">
      <span class="text-[11px] font-black text-softPin-inText truncate" title="${escapeHtml(pin.description)}">${escapeHtml(pin.description)}</span>
      <span class="w-1.5 h-1.5 rounded-full bg-softPin-inDot shrink-0"></span>
    </div>
    <div data-out="${escapeHtml(pin.name)}" class="flex items-center gap-1 font-mono">
      <input data-parameter="${escapeHtml(pin.name)}" aria-label="${escapeHtml(pin.description)}" type="number" step="any" value="${escapeHtml(value)}" ${canEdit ? "" : "disabled"} class="w-full min-w-0 px-1 py-0.5 text-right border border-softPin-inBorder rounded text-xs bg-white text-softPin-inText font-black disabled:bg-green-50/50 focus:outline-none focus:ring-1 focus:ring-green-400">
      <span class="shrink-0 text-[10px] text-emerald-900 font-bold">${escapeHtml(pin.unit)}</span>
    </div>
  </section>`;
}

function renderStepCard(step, formula, pins, expression, result, isSelected) {
  const rows = pins.inputs.map(pin => pinRow(pin, step.input_map[pin.name], "in", result[step.input_map[pin.name]])).join("");
  const outputs = pins.outputs.map(pin => pinRow(pin, step.output_map[pin.name], "out", result[step.output_map[pin.name]])).join("");
  return `<section data-node="step:${escapeHtml(step.step_id)}" class="flow-node-box node-step absolute rounded-lg overflow-visible ${isSelected ? "selected" : ""}">
    <div class="px-3 py-2 rounded-t-lg text-xs font-black border-b bg-softPin-opBg text-softPin-opText border-softPin-opBorder flex items-center justify-between">
      <span class="truncate">${escapeHtml(formula.name)}</span>
      <span class="w-2 h-2 rounded-full bg-softPin-opDot shrink-0"></span>
    </div>
    <div class="p-3 text-[11px] space-y-2 bg-white rounded-b-lg">
      ${expression ? `<div data-formula class="font-mono text-[10.5px] text-blue-900 bg-blue-50/70 border border-blue-100 rounded px-2 py-1 break-words leading-relaxed">${escapeHtml(expression)}</div>` : ''}
      ${rows ? `<div class="space-y-0.5">${rows}</div>` : ''}
      ${outputs ? `<div class="border-t border-dashed border-purple-200 pt-1.5 space-y-0.5">${outputs}</div>` : ''}
    </div>
  </section>`;
}

function computePlan2Layout(pipeline, sizes = {}) {
  const layout = {}, producers = new Map(), ranks = new Map();
  const steps = new Map(pipeline.steps.map(step => [step.step_id, step]));
  const inputNames = new Set(pipeline.required_inputs.map(pin => pin.name));
  const dimensions = key => sizes[key] || {width: key.startsWith("input:") ? 150 : 270, height: key.startsWith("input:") ? 60 : 260};
  for (const step of pipeline.steps) for (const variable of Object.values(step.output_map)) producers.set(variable, step.step_id);
  const parents = new Map(pipeline.steps.map(step => [step.step_id, new Set(
    Object.values(step.input_map).map(variable => producers.get(variable)).filter(id => id !== undefined)
  )]));

  // 仅使用真实来源关系分层，数组顺序和业务名称不决定计算流向。
  const pending = new Set(steps.keys()), ordered = [];
  while (pending.size) {
    let ready = [...pending].filter(id => [...parents.get(id)].every(parent => ranks.has(parent)));
    // 不完整或循环草稿仍可查看、修复；计算合法性由后端校验。
    if (!ready.length) ready = [pending.values().next().value];
    for (const id of ready) {
      ranks.set(id, Math.max(-1, ...[...parents.get(id)].map(parent => ranks.get(parent) ?? -1)) + 1);
      pending.delete(id); ordered.push(id);
    }
  }

  // 共享参数只放置一次，就近附着于最早使用它的算子。
  const attached = new Map(), placedInputs = new Set();
  for (const id of ordered) {
    const names = [...new Set(Object.values(steps.get(id).input_map))].filter(name => inputNames.has(name) && !placedInputs.has(name));
    attached.set(id, names);
    names.forEach(name => placedInputs.add(name));
  }
  const columns = new Map();
  for (const id of ordered) {
    const rank = ranks.get(id);
    if (!columns.has(rank)) columns.set(rank, []);
    columns.get(rank).push(id);
  }
  let left = 40, bottom = 20;
  for (const [rank, ids] of [...columns].sort((a, b) => a[0] - b[0])) {
    // 分支跟随上游所在行，汇合节点仍在所有上游的右侧。
    const parentTop = id => {
      const positions = [...parents.get(id)].map(parent => layout[`step:${parent}`]?.top).filter(top => top !== undefined);
      return positions.length ? Math.min(...positions) : 220;
    };
    ids.sort((a, b) => parentTop(a) - parentTop(b));
    let cursor = 20, columnWidth = 270;
    for (const id of ids) {
      const key = `step:${id}`, size = dimensions(key), names = attached.get(id);
      let inputTop = cursor, inputWidth = 0;
      for (let i = 0; i < names.length; i += 2) {
        let x = left, rowHeight = 0;
        for (const name of names.slice(i, i + 2)) {
          const inputKey = `input:${name}`, inputSize = dimensions(inputKey);
          layout[inputKey] = {left: x, top: inputTop};
          x += inputSize.width + 18;
          rowHeight = Math.max(rowHeight, inputSize.height);
        }
        inputWidth = Math.max(inputWidth, x - left - 18);
        inputTop += rowHeight + 18;
      }
      const top = Math.max(parentTop(id), names.length ? inputTop + 40 : cursor + 40);
      layout[key] = {left, top};
      columnWidth = Math.max(columnWidth, size.width, inputWidth);
      cursor = top + size.height + 100;
      bottom = Math.max(bottom, cursor);
    }
    left += columnWidth + 90;
  }
  // 未使用的参数保留在图中，放在现有卡片下方，方便后续连接。
  let unusedLeft = 40;
  for (const pin of pipeline.required_inputs) if (!placedInputs.has(pin.name)) {
    const key = `input:${pin.name}`;
    layout[key] = {left: unusedLeft, top: bottom};
    unusedLeft += dimensions(key).width + 18;
  }
  return layout;
}

function renderGraph() {
  const pipeline = sessionView.pipeline, calculation = sessionView.calculation_result;
  const result = Object.keys(pendingParameters).length ? {} : {...calculation?.initial_inputs, ...calculation?.final_outputs};
  const parameters = sessionView.inspected_parameters.filled_inputs || {};
  const canEdit = activeStage === 2 && !needsScenario();
  const html = [];

  for (const pin of pipeline.required_inputs) {
    const raw = pendingParameters[pin.name] ?? sessionView.provided_parameters[pin.name];
    const value = Object.hasOwn(pendingParameters, pin.name) ? pendingParameters[pin.name] ?? "" :
      parameters[pin.name] ?? (raw && typeof raw === "object" ? raw.value : raw) ?? pin.default_value ?? "";
    html.push(pin.kind === "constant" ? renderConstantCard(pin, value, canEdit) : renderInputCard(pin, value, canEdit));
  }

  for (const step of pipeline.steps) {
    const formula = formulaById(step.formula_id);
    const pins = effectivePins(formula, step);
    const expression = formula.display_expressions?.[step.solve_target || formula.default_target] || "";
    html.push(renderStepCard(step, formula, pins, expression, result, selectedStepId === step.step_id));
  }

  $("node-layer").innerHTML = html.join("");
  const nodes = [...$("node-layer").children];
  const sizes = Object.fromEntries(nodes.map(node => [node.dataset.node, {width: node.offsetWidth, height: node.offsetHeight}]));
  const defaultLayout = computePlan2Layout(pipeline, sizes);
  let maxRight = 1200, maxBottom = 800;

  nodes.forEach(node => {
    const key = node.dataset.node;
    const savedPos = pipeline.layout?.[key];
    const defaultPos = defaultLayout[key] || { left: 40, top: 200 };

    const left = savedPos ? savedPos.left : defaultPos.left;
    const top = savedPos ? savedPos.top : defaultPos.top;

    node.style.left = left + "px";
    node.style.top = top + "px";

    maxRight = Math.max(maxRight, left + node.offsetWidth + 80);
    maxBottom = Math.max(maxBottom, top + node.offsetHeight + 80);
  });

  $("dag-workspace").style.width = maxRight + "px";
  $("dag-workspace").style.height = maxBottom + "px";
  $("dag-workspace").style.transform = `translate(${panX}px, ${panY}px)`;

  $("tab-stage-1").classList.toggle("bg-white", activeStage === 1);
  $("tab-stage-2").classList.toggle("bg-white", activeStage === 2);
  $("tab-stage-1").disabled = !debugMode;
  $("tab-stage-2").disabled = !debugMode;
  $("stage-desc-hint").textContent = activeStage === 1 ? "流程拓扑审核" : "参数核对与计算结果";
  $("btn-main-action").textContent = needsScenario() ? "确认场景拓扑" : activeStage === 1 ? "核对参数" : "确认参数并计算";
  $("btn-main-action").hidden = !debugMode;
  positionToolbar(); scheduleWires();
}

function scheduleWires() {
  if (wireFrame !== null) cancelAnimationFrame(wireFrame);
  wireFrame = requestAnimationFrame(() => { wireFrame = null; drawWires(); });
}

function roundedWire(points) {
  if (!points.length) return "";
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const before = points[i - 1], corner = points[i], after = points[i + 1];
    const incoming = Math.hypot(corner.x - before.x, corner.y - before.y);
    const outgoing = Math.hypot(after.x - corner.x, after.y - corner.y);
    if (!incoming || !outgoing) continue;
    const radius = Math.min(6, incoming / 2, outgoing / 2);
    const start = {x: corner.x + (before.x - corner.x) * radius / incoming, y: corner.y + (before.y - corner.y) * radius / incoming};
    const end = {x: corner.x + (after.x - corner.x) * radius / outgoing, y: corner.y + (after.y - corner.y) * radius / outgoing};
    path += ` L ${start.x} ${start.y} Q ${corner.x} ${corner.y} ${end.x} ${end.y}`;
  }
  return path + ` L ${points.at(-1).x} ${points.at(-1).y}`;
}

function drawWires() {
  const workspace = $("dag-workspace").getBoundingClientRect(), nodes = [...$("node-layer").children];
  const rectangles = nodes.map(node => {
    const rect = node.getBoundingClientRect();
    return {left: rect.left - workspace.left, right: rect.right - workspace.left,
      top: rect.top - workspace.top, bottom: rect.bottom - workspace.top};
  });
  const obstacles = rectangles.map(rect => ({left: rect.left - 8, right: rect.right + 8, top: rect.top - 8, bottom: rect.bottom + 8}));
  const curve = document.createElementNS("http://www.w3.org/2000/svg", "path");
  const producers = new Map();
  for (const node of nodes) for (const port of node.querySelectorAll("[data-out]")) producers.set(port.dataset.out, {node, port});
  const paths = [];

  for (const node of nodes) for (const port of node.querySelectorAll("[data-in]")) {
    const varName = port.dataset.in;
    const source = producers.get(varName);
    port.classList.toggle("text-red-700", !source);
    port.title = source ? "" : "待连接输入来源";
    if (!source) continue;

    const sourceKey = source.node.dataset.node;
    const targetKey = node.dataset.node;

    const pa = source.port.getBoundingClientRect();
    const pb = port.getBoundingClientRect();
    const na = source.node.getBoundingClientRect();
    const nb = node.getBoundingClientRect();

    const from = { x: na.right - workspace.left, y: (pa.top + pa.bottom) / 2 - workspace.top };
    const to = { x: nb.left - workspace.left, y: (pb.top + pb.bottom) / 2 - workspace.top };

    let wireType = "wire-step";
    let markerId = "arrow-step";
    if (sourceKey.startsWith("input:")) {
      const isConst = source.node.classList.contains("node-constant");
      wireType = isConst ? "wire-constant" : "wire-input";
      markerId = isConst ? "arrow-const" : "arrow-input";
    }

    let activeClass = "";
    if (highlightedNode) {
      const isConnected = (sourceKey === highlightedNode.key || targetKey === highlightedNode.key);
      if (isConnected) {
        activeClass = "wire-highlight";
        markerId = "arrow-highlight";
      } else {
        activeClass = "wire-dimmed";
      }
    }

    let fromX = from.x, fromY = from.y;
    let isVerticalDrop = false;
    // 当输入卡片位于算子正上方时，从底部中点垂直引出并优雅进入左侧，根绝向外绕大圈
    if (sourceKey.startsWith("input:") && na.bottom <= nb.top + 30 && from.x >= to.x - 20) {
      fromX = (na.left + na.right) / 2 - workspace.left;
      fromY = na.bottom - workspace.top;
      isVerticalDrop = true;
    }

    let d = "";
    const dx = to.x - fromX;
    const dy = to.y - fromY;

    if (isVerticalDrop) {
      const dropY = (fromY + to.y) / 2;
      const leadX = to.x - 25;
      d = `M ${fromX} ${fromY} C ${fromX} ${dropY}, ${leadX} ${dropY}, ${to.x} ${to.y}`;
    } else if (dx > 20) {
      const curvature = Math.max(35, Math.min(160, dx * 0.42));
      d = `M ${fromX} ${fromY} C ${fromX + curvature} ${fromY}, ${to.x - curvature} ${to.y}, ${to.x} ${to.y}`;
    } else if (to.y > fromY + 40) {
      // 来源在上方、目标在下方或同一竖列：在两层卡片净空走廊中平滑向左拐入，绝不穿模
      const gapY = (na.bottom + nb.top) / 2 - workspace.top;
      const leadX = to.x - 30;
      d = `M ${fromX} ${fromY} C ${fromX + 25} ${fromY}, ${fromX + 25} ${gapY}, ${(fromX + leadX) / 2} ${gapY} S ${leadX} ${to.y}, ${to.x} ${to.y}`;
    } else {
      const offsetX = 35;
      const midY = (fromY + to.y) / 2;
      d = `M ${fromX} ${fromY} C ${fromX + offsetX} ${fromY}, ${fromX + offsetX} ${midY}, ${(fromX + to.x) / 2} ${midY} S ${to.x - offsetX} ${to.y}, ${to.x} ${to.y}`;
    }

    // 保留原曲线；只在曲线穿过卡片时，沿卡片外侧通道生成圆滑绕行线。
    curve.setAttribute("d", d);
    const length = curve.getTotalLength();
    let blocked = false;
    for (let distance = 4; distance < length; distance += 8) {
      const point = curve.getPointAtLength(distance);
      if (rectangles.some(rect => point.x > rect.left + 1 && point.x < rect.right - 1 && point.y > rect.top + 1 && point.y < rect.bottom - 1)) {
        blocked = true; break;
      }
    }
    if (blocked) {
      const start = {x: fromX, y: fromY};
      const exit = isVerticalDrop ? {x: fromX, y: fromY + 10} : {x: fromX + 10, y: fromY};
      const entry = {x: to.x - 20, y: to.y};
      const route = routeWire(exit, entry, obstacles);
      if (!route.length) {
        port.title = "卡片遮挡连线通道，请移开重叠卡片";
        continue;
      }
      d = roundedWire([start, ...route, to]);
    }
    paths.push(`<path class="wire-base ${wireType} ${activeClass}" data-from="${escapeHtml(sourceKey)}" data-to="${escapeHtml(targetKey)}" data-wire="${escapeHtml(varName)}" d="${d}" marker-end="url(#${markerId})"/>`);
  }

  const defs = $("svg-wiring-layer").querySelector("defs")?.outerHTML || `
    <defs>
      <marker id="arrow-step" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2563EB"/></marker>
      <marker id="arrow-input" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#16A34A"/></marker>
      <marker id="arrow-const" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#D97706"/></marker>
      <marker id="arrow-highlight" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2563EB"/></marker>
    </defs>
  `;
  $("svg-wiring-layer").innerHTML = defs + paths.join("");
}

function positionToolbar() {
  const node = [...$("node-layer").children].find(item => item.dataset.node === `step:${selectedStepId}`);
  $("node-floating-toolbar").classList.toggle("hidden", !node);
  if (node) { $("node-floating-toolbar").style.left = node.style.left; $("node-floating-toolbar").style.top = (parseFloat(node.style.top) - 35) + "px"; }
}
function sourceSelect(key, unit, excluded = [], variables = sessionView.variables) {
  const options = Object.entries(variables).filter(([variable, pin]) => (!unit || sameUnit(pin.unit, unit)) && !excluded.includes(variable));
  return `<select data-source="${escapeHtml(key)}" class="mt-1 w-full border rounded p-2"><option value="">请选择来源</option>${options.map(([variable, pin]) => `<option value="${escapeHtml(variable)}" ${variable === key ? "selected" : ""}>${escapeHtml(pin.description)} · ${escapeHtml(variable)} (${escapeHtml(pin.unit)})</option>`).join("")}</select>`;
}
function openDrawer(stepId) {
  selectedStepId = stepId; drawerPipeline = clone(sessionView.pipeline);
  const step = sessionView.pipeline.steps.find(item => item.step_id === stepId), formula = formulaById(step.formula_id);
  $("drawer-title").textContent = "算子属性与流水线操作";
  $("drawer-actions").classList.remove("hidden");
  $("drawer-formula-label").classList.remove("hidden"); $("drawer-desc-label").classList.remove("hidden");
  $("drawer-id").value = formula.id; $("drawer-name").value = formula.name;
  $("drawer-formula").value = formula.expression || "物性 / 查表函数"; $("drawer-formula").readOnly = formula.type !== "algebraic";
  $("drawer-desc").value = formula.description;
  $("drawer-target-label").classList.toggle("hidden", !formula.solve_targets.length);
  $("drawer-target").innerHTML = formula.solve_targets.map(name => {
    const pin = formula.variables.find(item => item.name === name);
    return `<option value="${escapeHtml(name)}" ${name === (step.solve_target || formula.default_target) ? "selected" : ""}>${escapeHtml(pin.description)} (${escapeHtml(pin.unit)})</option>`;
  }).join("");
  renderDrawerPins();
  $("operator-drawer").classList.remove("translate-x-full"); positionToolbar();
  for (const node of $("node-layer").children) node.classList.toggle("selected", node.dataset.node === `step:${stepId}`);
}
function renderDrawerPins() {
  const variables = Object.fromEntries(drawerPipeline.required_inputs.map(pin => [pin.name, pin]));
  for (const step of drawerPipeline.steps) {
    for (const pin of effectivePins(formulaById(step.formula_id), step).outputs) variables[step.output_map[pin.name]] = pin;
  }
  const step = drawerPipeline.steps.find(item => item.step_id === selectedStepId);
  const pins = effectivePins(formulaById(step.formula_id), step);
  $("drawer-pins").innerHTML = pins.inputs.map(pin => `<label class="block font-bold" data-pin="${escapeHtml(pin.name)}">${escapeHtml(pin.description)} (${escapeHtml(pin.unit)})${sourceSelect(step.input_map[pin.name], pin.unit, Object.values(step.output_map), variables)}</label>`).join("");
}
function changeSolveTarget() {
  const step = sessionView.pipeline.steps.find(item => item.step_id === selectedStepId);
  drawerPipeline = configureTarget(sessionView.pipeline, selectedStepId, formulaById(step.formula_id), $("drawer-target").value);
  renderDrawerPins();
}
function closeDrawer() { $("operator-drawer").classList.add("translate-x-full"); drawerPipeline = null; }
function saveDrawer() {
  const stepId = selectedStepId, pipeline = clone(drawerPipeline);
  const name = $("drawer-name").value, expression = $("drawer-formula").value, description = $("drawer-desc").value;
  const sources = [...$("drawer-pins").querySelectorAll("select")].map(select => ({pin: select.parentElement.dataset.pin, value: select.value}));
  return enqueue(async () => {
    const step = pipeline.steps.find(item => item.step_id === stepId), formula = formulaById(step.formula_id);
    sources.forEach(item => { step.input_map[item.pin] = item.value; });
    const originalInputs = new Set(sessionView.pipeline.required_inputs.map(pin => pin.name));
    const used = new Set(pipeline.steps.flatMap(item => Object.values(item.input_map)));
    pipeline.required_inputs = pipeline.required_inputs.filter(pin => originalInputs.has(pin.name) || used.has(pin.name));
    if (name !== formula.name || (formula.type === "algebraic" && expression !== formula.expression) || description !== formula.description) {
      await api("/api/operator/update", {operator_id: formula.id, name, formula: formula.type === "algebraic" ? expression : null, description});
    }
    await savePipeline(pipeline); closeDrawer();
  });
}

function openAddOperatorModal(mode = "after", anchor = selectedStepId) {
  if (!sessionView) return;
  insertionMode = mode; insertionAnchor = anchor;
  $("modal-title").textContent = ({before: "在节点前插入算子", after: "在节点后插入算子", replace: "替换当前算子"})[mode];
  $("select-lib-op").innerHTML = sessionView.formulas.map(formula => `<option value="${escapeHtml(formula.id)}">${escapeHtml(formula.name)} · ${escapeHtml(formula.id)}</option>`).join("") + '<option value="__new__">创建新的代数算子…</option>';
  changeOperatorSelection(); $("modal-add-op").classList.remove("hidden");
}
function closeAddOperatorModal() { $("modal-add-op").classList.add("hidden"); }
function changeOperatorSelection() { $("new-operator-fields").classList.toggle("hidden", $("select-lib-op").value !== "__new__"); }
function triggerInsertBefore() { openAddOperatorModal("before"); }
function triggerInsertAfter() { openAddOperatorModal("after"); }
function triggerReplace() { if (selectedStepId) openAddOperatorModal("replace"); }
function triggerDeleteCurrent() {
  const stepId = selectedStepId;
  if (!stepId) return;
  return enqueue(async () => {
    const pipeline = clone(sessionView.pipeline);
    pipeline.steps = pipeline.steps.filter(step => step.step_id !== stepId);
    delete pipeline.layout[`step:${stepId}`];
    await savePipeline(pipeline); selectedStepId = null; closeDrawer(); positionToolbar();
  });
}
function buildNewPinFields(silent = false) {
  const parts = $("new-eq").value.split("=");
  const output = parts[0]?.trim();
  if (parts.length !== 2 || !/^[A-Za-z][A-Za-z0-9_]*$/.test(output)) {
    if (!silent) showMessage("新算子请使用 y = 表达式，并明确各引脚单位");
    return;
  }
  const inputs = [...new Set(parts[1].match(/[A-Za-z][A-Za-z0-9_]*/g) || [])];
  const previous = new Map([...$("new-pins").children].map(row => [row.dataset.pinName, {unit: row.querySelector("[data-unit]").value, description: row.querySelector("[data-description]").value}]));
  $("new-pins").innerHTML = [...inputs.map(name => ({name, kind: "input"})), {name: output, kind: "output"}].map(pin => {
    const saved = previous.get(pin.name);
    return `<div data-pin-name="${escapeHtml(pin.name)}" data-pin-kind="${pin.kind}" class="grid grid-cols-3 gap-2 items-center"><span>${pin.kind === "input" ? "输入" : "输出"} ${escapeHtml(pin.name)}</span><input data-description aria-label="${escapeHtml(pin.name)} 名称" placeholder="中文名称" value="${escapeHtml(saved?.description || pin.name)}" class="border rounded p-2"><input data-unit aria-label="${escapeHtml(pin.name)} 单位" placeholder="单位" value="${escapeHtml(saved?.unit || "/")}" class="border rounded p-2"></div>`;
  }).join("");
}
function confirmNewOperator() {
  const mode = insertionMode, anchor = insertionAnchor, chosen = $("select-lib-op").value;
  let payload;
  if (chosen === "__new__") {
    buildNewPinFields();
    payload = {id: $("new-id").value.trim(), name: $("new-name").value.trim(), equation: $("new-eq").value, inputs: [], outputs: []};
    for (const row of $("new-pins").children) payload[row.dataset.pinKind === "input" ? "inputs" : "outputs"].push({name: row.dataset.pinName, description: row.querySelector("[data-description]").value, unit: row.querySelector("[data-unit]").value});
  }
  return enqueue(async () => {
    if (payload) { await api("/api/operator/add", payload); sessionView.formulas = (await api("/api/formulas")).formulas; }
    const formula = formulaById(payload ? payload.id : chosen), pipeline = clone(sessionView.pipeline);
    const step = makeStep(pipeline, formula, sessionView.variables, anchor, mode);
    const index = pipeline.steps.findIndex(item => item.step_id === anchor);
    if (mode === "replace" && index >= 0) {
      step.step_id = anchor; pipeline.steps.splice(index, 1, step);
    } else pipeline.steps.splice(index < 0 ? pipeline.steps.length : index + (mode === "after" ? 1 : 0), 0, step);
    await savePipeline(pipeline); closeAddOperatorModal(); openDrawer(step.step_id);
  });
}
function openAddConstantModal() { $("modal-add-const").classList.remove("hidden"); }
function closeAddConstantModal() { $("modal-add-const").classList.add("hidden"); }
function confirmNewConstant() {
  const raw = $("new-const-val").value;
  const pin = {name: $("new-const-id").value.trim(), description: $("new-const-name").value.trim(), unit: $("new-const-unit").value.trim(), default_value: Number(raw), kind: "constant"};
  return enqueue(async () => {
    if (raw === "" || !Number.isFinite(pin.default_value)) throw new Error("请填写有限的常量数值");
    const pipeline = clone(sessionView.pipeline); pipeline.required_inputs.push(pin);
    await savePipeline(pipeline); closeAddConstantModal();
  });
}
function resetLayoutPositions() {
  return enqueue(async () => { const pipeline = clone(sessionView.pipeline); pipeline.layout = {}; panX = 0; panY = 0; await savePipeline(pipeline); });
}

function initializeEditor() {
  const canvas = $("canvas-container");
  canvas.addEventListener("mouseover", event => {
    const node = event.target.closest("[data-node]");
    if (node && (!highlightedNode || highlightedNode.node !== node)) {
      highlightedNode = { node, key: node.dataset.node };
      scheduleWires();
    }
  });
  canvas.addEventListener("mouseout", event => {
    const node = event.target.closest("[data-node]");
    if (node && !event.relatedTarget?.closest(`[data-node="${node.dataset.node}"]`)) {
      highlightedNode = null;
      scheduleWires();
    }
  });
  canvas.addEventListener("input", event => {
    const name = event.target.dataset.parameter;
    if (!name) return;
    pendingParameters[name] = event.target.value === "" ? null : Number(event.target.value);
    // 尚未提交的新参数也不能继续展示旧工况成果。
    for (const value of canvas.querySelectorAll("[data-value]")) value.textContent = "—";
  });
  canvas.addEventListener("change", event => {
    const name = event.target.dataset.parameter;
    if (!name) return;
    const parameters = takePendingParameters();
    parameters[name] = event.target.value === "" ? null : Number(event.target.value);
    enqueue(async () => {
      await api(sessionUrl + "/parameters", {parameters});
      await syncFromBackend();
      showMessage("参数已保存，旧结果已失效。请重新确认参数后再执行计算。");
    });
  });
  canvas.addEventListener("pointerdown", event => {
    if (busy || event.button !== 0 || event.target.closest("input,button,select,textarea")) return;
    const node = event.target.closest("[data-node]");
    drag = {node, startX: event.clientX, startY: event.clientY, left: node ? parseFloat(node.style.left) : panX, top: node ? parseFloat(node.style.top) : panY, moved: false, pointerId: event.pointerId};
    canvas.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", event => {
    if (!drag) return;
    const dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
    if (Math.abs(dx) + Math.abs(dy) > 5) drag.moved = true;
    if (!drag.moved) return;
    if (drag.node) { drag.node.style.left = drag.left + dx + "px"; drag.node.style.top = drag.top + dy + "px"; positionToolbar(); scheduleWires(); }
    else { panX = drag.left + dx; panY = drag.top + dy; $("dag-workspace").style.transform = `translate(${panX}px, ${panY}px)`; }
  });
  canvas.addEventListener("pointerup", event => {
    if (!drag) return;
    const current = drag; drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (current.moved && current.node) {
      const key = current.node.dataset.node, position = {left: parseFloat(current.node.style.left), top: parseFloat(current.node.style.top)};
      enqueue(async () => { const pipeline = clone(sessionView.pipeline); pipeline.layout[key] = position; await savePipeline(pipeline); });
    } else if (!current.moved) {
      const key = current.node?.dataset.node || "";
      if (key.startsWith("step:")) openDrawer(key.slice(5));
      else { selectedStepId = null; closeDrawer(); positionToolbar(); }
    }
  });
  canvas.addEventListener("pointercancel", () => { drag = null; renderGraph(); });
  canvas.addEventListener("wheel", event => {
    if (event.target.closest("input,select")) return;
    event.preventDefault(); panX -= event.deltaX; panY -= event.deltaY;
    $("dag-workspace").style.transform = `translate(${panX}px, ${panY}px)`;
  }, {passive: false});
  window.addEventListener("resize", scheduleWires);
  enqueue(syncFromBackend);
  // 同步 AI 的阶段命令和计算结果；本地编辑期间不覆盖尚未提交的输入。
  if (typeof setInterval !== "undefined") setInterval(() => {
    if (busy || drag || drawerPipeline || Object.keys(pendingParameters).length ||
        document.activeElement?.matches("input,select,textarea")) return;
    enqueue(syncFromBackend);
  }, 1000);
}

if (typeof module !== "undefined") module.exports = {routeWire, makeStep, sameUnit, escapeHtml, effectivePins, configureTarget};
if (typeof document !== "undefined") initializeEditor();
