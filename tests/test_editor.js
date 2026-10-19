const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const {routeWire, makeStep, escapeHtml, configureTarget, effectivePins} = require('../ui_editor.js');

const powerFormula = {
  id: 'power', default_target: 'power', solve_targets: ['flow', 'difference', 'power'],
  variables: [{name: 'flow', unit: 't/h', description: '蒸汽流量', default_value: 100},
    {name: 'difference', unit: 'kJ/kg', description: '焓差'}, {name: 'power', unit: 'MW', description: '功率'}],
};
const powerPipeline = () => ({layout: {}, required_inputs: powerFormula.variables.slice(0, 2), steps: [
  {step_id: 'power_step', formula_id: 'power', input_map: {flow: 'flow', difference: 'difference'}, output_map: {power: 'power'}},
  {step_id: 'consumer', formula_id: 'other', input_map: {flow: 'flow', power: 'power'}, output_map: {answer: 'answer'}},
]});

test('选择待求量只修改节点草稿，调整输入输出并保留下游引用', () => {
  const original = powerPipeline(), before = JSON.stringify(original);
  const inverse = configureTarget(original, 'power_step', powerFormula, 'flow');
  assert.equal(JSON.stringify(original), before);
  assert.deepEqual(inverse.steps[0].input_map, {difference: 'difference', power: 'power'});
  assert.deepEqual(inverse.steps[0].output_map, {flow: 'flow'});
  assert.deepEqual(inverse.steps[1], original.steps[1]);
  assert.deepEqual(inverse.required_inputs.map(pin => pin.name), ['difference', 'power']);
  assert.equal(inverse.required_inputs.find(pin => pin.name === 'power').default_value, null);
  assert.deepEqual(effectivePins(powerFormula, inverse.steps[0]).outputs.map(pin => pin.name), ['flow']);
  const forward = configureTarget(inverse, 'power_step', powerFormula, 'power');
  assert.deepEqual(forward.steps[0].output_map, {power: 'power'});
  assert.equal(forward.required_inputs.find(pin => pin.name === 'flow').default_value, null);
});

test('原目标来自另一个算子时，创建独立输出，不覆盖上游变量', () => {
  const pipeline = powerPipeline();
  pipeline.required_inputs = pipeline.required_inputs.filter(pin => pin.name !== 'flow');
  pipeline.steps.unshift({step_id: 'producer', formula_id: 'other', input_map: {}, output_map: {flow: 'flow'}});
  const inverse = configureTarget(pipeline, 'power_step', powerFormula, 'flow');
  assert.equal(inverse.steps[0].output_map.flow, 'flow');
  assert.equal(inverse.steps[1].output_map.flow, 'flow_2');
  assert.equal(inverse.steps[2].input_map.flow, 'flow');
});

test('同一来源同时绑定多个已知量时不移除该来源', () => {
  const pipeline = powerPipeline();
  pipeline.steps[0].input_map.difference = 'flow';
  const inverse = configureTarget(pipeline, 'power_step', powerFormula, 'flow');
  assert.ok(inverse.required_inputs.some(pin => pin.name === 'flow'));
  assert.equal(inverse.steps[0].output_map.flow, 'flow_2');
});

test('用同一个算子替换反算节点，保留该节点的求解方向', () => {
  const pipeline = configureTarget(powerPipeline(), 'power_step', powerFormula, 'flow');
  const variables = Object.fromEntries(powerFormula.variables.map(pin => [pin.name, pin]));
  const step = makeStep(pipeline, powerFormula, variables, 'power_step', 'replace');
  assert.equal(step.solve_target, 'flow');
  assert.deepEqual(step.input_map, pipeline.steps[0].input_map);
  assert.deepEqual(step.output_map, pipeline.steps[0].output_map);
});

test('正交线路绕过第三方卡片，包括折返与逆向连接', () => {
  const obstacles = [{left: 40, right: 160, top: -20, bottom: 20}, {left: 80, right: 130, top: 20, bottom: 100}];
  for (const [start, end] of [[{x: 0, y: 0}, {x: 200, y: 0}], [{x: 200, y: 0}, {x: 0, y: 80}]]) {
    const path = routeWire(start, end, obstacles);
    assert.ok(path.length >= 4);
    assert.deepEqual(path[0], start); assert.deepEqual(path.at(-1), end);
    path.slice(1).forEach((b, i) => {
      const a = path[i];
      assert.ok(a.x === b.x || a.y === b.y);
      for (const r of obstacles) assert.equal(a.x === b.x
        ? a.x > r.left && a.x < r.right && Math.max(a.y, b.y) > r.top && Math.min(a.y, b.y) < r.bottom
        : a.y > r.top && a.y < r.bottom && Math.max(a.x, b.x) > r.left && Math.min(a.x, b.x) < r.right, false);
    });
  }
});

test('替换保留下游变量，重复插入生成独立步骤及变量', () => {
  const formula = {id: 'custom.double', inputs: [{name:'x',unit:'MW'}], outputs:[{name:'y',unit:'MW'}]};
  const pipeline = {steps:[{step_id:'custom_double', input_map:{x:'source'}, output_map:{y:'answer'}}]};
  const variables = {source:{unit:'MW'},answer:{unit:'MW'},y:{unit:'MW'}};
  const replacement = makeStep(pipeline, formula, variables, 'custom_double', 'replace');
  assert.deepEqual(replacement.input_map, {x:'source'});
  assert.deepEqual(replacement.output_map, {y:'answer'});
  const inserted = makeStep(pipeline, formula, variables, 'custom_double', 'after');
  assert.equal(inserted.step_id, 'custom_double_2');
  assert.equal(inserted.output_map.y, 'y_2');
});

test('算子名称不作为 HTML 执行', () => {
  assert.equal(escapeHtml('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
});

// 覆盖真实输入事件→确认按钮调用顺序，不依赖浏览器是否额外发出 change。
function editorHarness(status = 200, search = '', stubSync = true) {
  const listeners = {}, requests = [], output = {textContent:'旧成果'};
  const elements = {
    'canvas-container': {addEventListener:(name, callback)=>listeners[name]=callback, querySelectorAll:()=>[output]},
    'btn-main-action': {},
    'editor-message': {textContent:'',classList:{toggle(){}}},
  };
  const context = vm.createContext({console, URLSearchParams, setTimeout, clearTimeout, location: {search}});
  vm.runInContext(readFileSync(require.resolve('../ui_editor.js'),'utf8'), context);
  context.document = {getElementById:id=>elements[id]};
  context.window = {addEventListener(){}};
  context.fetch = async (url, options) => {
    requests.push({url,body:options.body && JSON.parse(options.body)});
    return {ok:status===200,status,json:async()=>status===200 ? {is_complete:true} : {error:'测试接口拒绝'}};
  };
  const syncFromBackend = vm.runInContext('syncFromBackend', context);
  vm.runInContext('syncFromBackend = async () => {};', context);
  vm.runInContext(`debugMode = true; sessionView = {current_state:'CALCULATED',inspected_parameters:{filled_inputs:{x:3}}}; activeStage = 2; initializeEditor();`,context);
  if (!stubSync) context.syncFromBackend = syncFromBackend;
  return {context,listeners,requests,output,elements};
}

test('输入后直接确认使用新值，零值不被默认值覆盖', async () => {
  const h = editorHarness();
  h.listeners.input({target:{dataset:{parameter:'x'},value:'0'}});
  assert.equal(h.output.textContent,'—');
  await vm.runInContext('handlePrimaryAction()',h.context);
  assert.deepEqual(h.requests.map(r=>r.body), [{parameters:{x:0}},{confirmed:true},{}]);
});

test('普通模式前端不能自行切换阶段或确认计算', async () => {
  const h = editorHarness();
  vm.runInContext('debugMode = false; activeStage = 1;', h.context);
  await vm.runInContext('switchStage(2); handlePrimaryAction(); mutationQueue', h.context);
  assert.equal(vm.runInContext('activeStage', h.context), 1);
  assert.equal(h.requests.length, 0);
});

test('调试模式可以在前端切换阶段', async () => {
  const h = editorHarness();
  vm.runInContext('activeStage = 1; renderGraph = () => {};', h.context);
  await vm.runInContext('switchStage(2); mutationQueue', h.context);
  assert.equal(vm.runInContext('activeStage', h.context), 2);
  assert.equal(h.requests.length, 0);
});

test('参数微调只保存新值，不确认、不计算', async () => {
  const h = editorHarness();
  h.listeners.input({target:{dataset:{parameter:'x'},value:'7'}});
  h.listeners.change({target:{dataset:{parameter:'x'},value:'7'}});
  await vm.runInContext('mutationQueue', h.context);
  assert.deepEqual(h.requests.map(item => item.url), ['/api/session/default/parameters']);
  assert.equal(h.output.textContent, '—');
  assert.match(h.elements['editor-message'].textContent, /重新确认/);
});

test('普通页面忽略 URL 阶段，按 AI 后端命令同步阶段且不确认计算', async () => {
  let stage = 1;
  const requests = [];
  const context = vm.createContext({URLSearchParams, location:{search:'?stage=2'}});
  vm.runInContext(readFileSync(require.resolve('../ui_editor.js'), 'utf8'), context);
  context.fetch = async url => {
    requests.push(url);
    return {ok:true, json:async()=>({editor_debug:false, editor_stage:stage,
      current_state:'PARAMETERS_INSPECTED', validation:{errors:[]}})};
  };
  vm.runInContext('renderGraph = () => {}; showMessage = () => {};', context);
  await vm.runInContext('syncFromBackend()', context);
  assert.equal(vm.runInContext('activeStage', context), 1);
  stage = 2;
  await vm.runInContext('syncFromBackend()', context);
  assert.equal(vm.runInContext('activeStage', context), 2);
  assert.deepEqual(requests, ['/api/session/default', '/api/session/default']);
});

for (const status of [400,422,500]) test(`HTTP ${status} 后不继续确认或计算`, async () => {
  const h = editorHarness(status);
  await vm.runInContext('handlePrimaryAction()',h.context);
  assert.equal(h.requests.length,1);
  assert.equal(h.elements['editor-message'].textContent,'测试接口拒绝');
});

test('断网时展示错误，不继续确认或计算', async () => {
  const h = editorHarness();
  h.context.fetch = async () => {throw new Error('网络断开');};
  await vm.runInContext('handlePrimaryAction()',h.context);
  assert.equal(h.elements['editor-message'].textContent,'网络断开');
});

test('指定流水线的页面仍然调用正确的确认和计算路径', async () => {
  const h = editorHarness(200, '?session_id=custom&pipeline=other&reset=1');
  await vm.runInContext('handlePrimaryAction()', h.context);
  assert.deepEqual(h.requests.map(item => item.url), [
    '/api/session/custom/parameters', '/api/session/custom/confirm_parameters', '/api/session/custom/calculate',
  ]);
});

function layoutFor(pipeline, sizes = {}) {
  const context = vm.createContext({URLSearchParams, pipeline, sizes});
  vm.runInContext(readFileSync(require.resolve('../ui_editor.js'), 'utf8'), context);
  return JSON.parse(vm.runInContext('JSON.stringify(computePlan2Layout(pipeline, sizes))', context));
}

function previewHarness() {
  const h = editorHarness(200, '', false);
  for (const id of ['btn-preview-calculation', 'preview-notice', 'tab-stage-1', 'tab-stage-2',
    'stage-desc-hint', 'node-floating-toolbar', 'dag-workspace']) {
    h.elements[id] = {style: {}, classList: {toggle() {}}};
  }
  h.elements['node-layer'] = {innerHTML: '', children: []};
  h.context.requestAnimationFrame = () => 0;
  h.context.cancelAnimationFrame = () => {};
  vm.runInContext(`debugMode = false; activeStage = 2; sessionView = {
    current_state: 'PARAMETERS_INSPECTED', calculation_result: null,
    inspected_parameters: {filled_inputs: {x: 3}}, provided_parameters: {x: 3},
    pipeline: {id: 'preview', required_inputs: [{name: 'x', unit: 'MW', description: '输入'}],
      steps: [{step_id: 'double', formula_id: 'double', input_map: {x: 'x'}, output_map: {y: 'answer'}}]},
    formulas: [{id: 'double', name: '翻倍', inputs: [{name: 'x', unit: 'MW'}],
      outputs: [{name: 'y', unit: 'MW'}]}]
  };`, h.context);
  h.context.fetch = async (url, options) => {
    h.requests.push({url, body: JSON.parse(options.body)});
    return {ok: true, json: async () => ({preview_result: {initial_inputs: {x: 7}, final_outputs: {answer: 14}}})};
  };
  return h;
}

test('阶段02普通模式可预览未提交参数，不确认、不保存、不改变正式成果', async () => {
  const h = previewHarness();
  const before = vm.runInContext('JSON.stringify(sessionView)', h.context);
  h.listeners.input({target: {dataset: {parameter: 'x'}, value: '7'}});
  await vm.runInContext('handlePreviewCalculation()', h.context);
  assert.deepEqual(h.requests.map(item => item.url), ['/api/preview_calculation']);
  assert.deepEqual(h.requests[0].body.parameters, {x: 7});
  assert.equal(vm.runInContext('pendingParameters.x', h.context), 7);
  assert.equal(vm.runInContext('JSON.stringify(sessionView)', h.context), before);
  assert.match(h.elements['node-layer'].innerHTML, /data-value="answer">14</);
  assert.equal(h.elements['preview-notice'].hidden, false);
});

test('阶段01隐藏预览，切到阶段02才显示，未确认场景不能预览', async () => {
  const h = previewHarness();
  vm.runInContext('activeStage = 1; renderGraph()', h.context);
  assert.equal(h.elements['btn-preview-calculation'].hidden, true);
  await vm.runInContext('handlePreviewCalculation()', h.context);
  assert.equal(h.requests.length, 0);
  vm.runInContext('activeStage = 2; renderGraph()', h.context);
  assert.equal(h.elements['btn-preview-calculation'].hidden, false);
  assert.equal(h.elements['btn-main-action'].hidden, true);
  vm.runInContext("sessionView.current_state = 'SCENARIO_PROPOSED'; renderGraph()", h.context);
  await vm.runInContext('handlePreviewCalculation()', h.context);
  assert.equal(h.elements['btn-preview-calculation'].disabled, true);
  assert.equal(h.requests.length, 0);
});

test('编辑参数立即隐藏旧预览标注和数值', async () => {
  const h = previewHarness();
  await vm.runInContext('handlePreviewCalculation()', h.context);
  h.listeners.input({target: {dataset: {parameter: 'x'}, value: '8'}});
  assert.equal(h.elements['preview-notice'].hidden, true);
  assert.equal(h.output.textContent, '—');
});

test('后台正式状态变化后，轮询同步清除预览', async () => {
  const h = previewHarness();
  await vm.runInContext('handlePreviewCalculation()', h.context);
  const next = JSON.parse(vm.runInContext('JSON.stringify(sessionView)', h.context));
  next.current_state = 'CALCULATED';
  next.calculation_result = {initial_inputs: {x: 3}, final_outputs: {answer: 6}};
  next.editor_stage = 2;
  h.context.fetch = async () => ({ok: true, json: async () => next});
  await vm.runInContext('syncFromBackend()', h.context);
  assert.equal(h.elements['preview-notice'].hidden, true);
  assert.match(h.elements['node-layer'].innerHTML, /data-value="answer">6</);
  assert.equal(vm.runInContext('previewCalculation', h.context), null);
});

test('预览失败不调用会话同步或确认接口，也不留下旧预览', async () => {
  const h = previewHarness();
  await vm.runInContext('handlePreviewCalculation()', h.context);
  const before = vm.runInContext('JSON.stringify(sessionView)', h.context);
  h.context.fetch = async (url, options) => {
    h.requests.push({url, body: JSON.parse(options.body)});
    return {ok: false, status: 400, json: async () => ({error: '缺少已知量'})};
  };
  await vm.runInContext('handlePreviewCalculation()', h.context);
  assert.deepEqual(h.requests.map(item => item.url), ['/api/preview_calculation', '/api/preview_calculation']);
  assert.equal(vm.runInContext('JSON.stringify(sessionView)', h.context), before);
  assert.equal(h.elements['preview-notice'].hidden, true);
  assert.match(h.elements['editor-message'].textContent, /缺少已知量/);
});

test('预览请求期间参数变化时，不展示过期返回值', async () => {
  const h = previewHarness();
  let release;
  h.context.fetch = () => new Promise(resolve => { release = resolve; });
  const preview = vm.runInContext('handlePreviewCalculation()', h.context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.elements['btn-preview-calculation'].disabled, true);
  h.listeners.input({target: {dataset: {parameter: 'x'}, value: '8'}});
  release({ok: true, json: async () => ({preview_result: {initial_inputs: {x: 3}, final_outputs: {answer: 6}}})});
  await preview;
  assert.equal(h.elements['preview-notice'].hidden, true);
  assert.match(h.elements['editor-message'].textContent, /已变化/);
  assert.doesNotMatch(h.elements['node-layer'].innerHTML, /data-value="answer">6</);
});

test('陌生场景仅布局实际节点，首个算子位于初始视口内', () => {
  const layout = layoutFor({required_inputs: [{name: 'quantity'}], steps: [
    {step_id: 'custom', input_map: {x: 'quantity'}, output_map: {y: 'answer'}},
  ]});
  assert.deepEqual(Object.keys(layout).sort(), ['input:quantity', 'step:custom']);
  assert.ok(layout['step:custom'].left < 600);
  assert.ok(layout['input:quantity'].top < layout['step:custom'].top);
});

test('按真实依赖向右分流排布，不依赖步骤名称和数组顺序', () => {
  const pipeline = {required_inputs: [{name: 'x'}], steps: [
    {step_id: 'join', input_map: {a: 'left', b: 'right'}, output_map: {z: 'answer'}},
    {step_id: 'right', input_map: {a: 'seed'}, output_map: {z: 'right'}},
    {step_id: 'root', input_map: {a: 'x'}, output_map: {z: 'seed'}},
    {step_id: 'left', input_map: {a: 'seed'}, output_map: {z: 'left'}},
  ]};
  const layout = layoutFor(pipeline);
  for (const child of ['left', 'right']) {
    assert.ok(layout['step:root'].left < layout[`step:${child}`].left);
    assert.ok(layout[`step:${child}`].left < layout['step:join'].left);
  }
  assert.notEqual(layout['step:left'].top, layout['step:right'].top);
});

test('reset 和场景选择只用于首次读取，后续同步不会丢失草稿', async () => {
  const search = '?session_id=custom&pipeline=other&reset=1';
  const replaced = [];
  const context = vm.createContext({URLSearchParams, URL, location: {search, href: `http://localhost/editor${search}`},
    history: {replaceState: (_, title, url) => replaced.push(String(url))}});
  vm.runInContext(readFileSync(require.resolve('../ui_editor.js'), 'utf8'), context);
  const urls = [];
  context.fetch = async url => {
    urls.push(url);
    return {ok: true, json: async () => ({current_state: 'SCENARIO_PROPOSED', validation: {errors: []}})};
  };
  vm.runInContext('renderGraph = () => {}; showMessage = () => {};', context);
  await vm.runInContext('syncFromBackend()', context);
  await vm.runInContext('syncFromBackend()', context);
  assert.deepEqual(urls, ['/api/session/custom?pipeline=other&reset=1', '/api/session/custom']);
  assert.deepEqual(replaced, ['http://localhost/editor?session_id=custom&pipeline=other']);
});

test('大算子、多输入和共享常量按实际尺寸排布，无重复胶囊或卡片重叠', () => {
  const pipeline = {required_inputs: Array.from({length: 7}, (_, i) => ({name: `p${i}`})), steps: [
    {step_id: 'tall', input_map: Object.fromEntries(Array.from({length: 6}, (_, i) => [`v${i}`, `p${i}`])), output_map: {y: 'a'}},
    {step_id: 'parallel', input_map: {x: 'p0', y: 'p6'}, output_map: {y: 'b'}},
  ]};
  const sizes = Object.fromEntries(pipeline.required_inputs.map(pin => [`input:${pin.name}`, {width: 150, height: 70}]));
  sizes['step:tall'] = {width: 270, height: 600};
  sizes['step:parallel'] = {width: 270, height: 260};
  const layout = layoutFor(pipeline, sizes), keys = Object.keys(layout);
  assert.equal(keys.length, 9);
  for (let i = 0; i < keys.length; i++) for (let j = i + 1; j < keys.length; j++) {
    const a = layout[keys[i]], b = layout[keys[j]], sa = sizes[keys[i]], sb = sizes[keys[j]];
    assert.ok(a.left + sa.width <= b.left || b.left + sb.width <= a.left ||
      a.top + sa.height <= b.top || b.top + sb.height <= a.top, `${keys[i]} overlaps ${keys[j]}`);
  }
});

test('缺失来源和循环草稿仍能有限排布，仅由后端决定是否允许计算', () => {
  const pipeline = {required_inputs: [{name: 'unused'}], steps: [
    {step_id: 'a', input_map: {x: 'b'}, output_map: {y: 'a'}},
    {step_id: 'b', input_map: {x: 'a', z: 'missing'}, output_map: {y: 'b'}},
  ]};
  const layout = layoutFor(pipeline);
  assert.equal(Object.keys(layout).length, 3);
  assert.ok(Object.values(layout).every(p => Number.isFinite(p.left) && Number.isFinite(p.top)));
});

test('胶囊间只有 18px 间距时，绕行曲线仍有出口且保留圆角', () => {
  const context = vm.createContext({URLSearchParams});
  vm.runInContext(readFileSync(require.resolve('../ui_editor.js'), 'utf8'), context);
  // 150px 胶囊之间保持当前界面间距，不能扩大避障边界封死通道。
  const rectangles = [{left: 0, right: 150, top: 0, bottom: 60},
    {left: 168, right: 318, top: 0, bottom: 60},
    {left: 0, right: 270, top: 220, bottom: 400}];
  const obstacles = rectangles.map(r => ({left: r.left - 8, right: r.right + 8, top: r.top - 8, bottom: r.bottom + 8}));
  const route = routeWire({x: 160, y: 30}, {x: -20, y: 300}, obstacles);
  assert.ok(route.length > 2);
  context.points = [{x: 150, y: 30}, ...route, {x: 0, y: 300}];
  const path = vm.runInContext('roundedWire(points)', context);
  assert.ok(path.startsWith('M 150 30') && path.endsWith('L 0 300'));
  assert.ok(path.includes(' Q '));
  assert.ok(!path.includes('NaN'));
});
