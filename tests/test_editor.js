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
function editorHarness(status = 200) {
  const listeners = {}, requests = [], output = {textContent:'旧成果'};
  const elements = {
    'canvas-container': {addEventListener:(name, callback)=>listeners[name]=callback, querySelectorAll:()=>[output]},
    'btn-main-action': {},
    'editor-message': {textContent:'',classList:{toggle(){}}},
  };
  const context = vm.createContext({console, URLSearchParams, setTimeout, clearTimeout});
  vm.runInContext(readFileSync(require.resolve('../ui_editor.js'),'utf8'), context);
  context.document = {getElementById:id=>elements[id]};
  context.window = {addEventListener(){}};
  context.fetch = async (url, options) => {
    requests.push({url,body:options.body && JSON.parse(options.body)});
    return {ok:status===200,status,json:async()=>status===200 ? {is_complete:true} : {error:'测试接口拒绝'}};
  };
  vm.runInContext(`syncFromBackend = async () => {}; sessionView = {current_state:'CALCULATED',inspected_parameters:{filled_inputs:{x:3}}}; activeStage = 2; initializeEditor();`,context);
  return {context,listeners,requests,output,elements};
}

test('输入后直接确认使用新值，零值不被默认值覆盖', async () => {
  const h = editorHarness();
  h.listeners.input({target:{dataset:{parameter:'x'},value:'0'}});
  assert.equal(h.output.textContent,'—');
  await vm.runInContext('handlePrimaryAction()',h.context);
  assert.deepEqual(h.requests.map(r=>r.body), [{parameters:{x:0}},{confirmed:true},{}]);
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
