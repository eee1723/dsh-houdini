import assert from 'node:assert/strict';
import {
  collectValidationCoverage,
  collectRetryWork,
  collectQualityLoopEvidence,
  completedVisionTodoWithoutEvidence,
  execResultFromPreview,
  classifyVisionEvidence,
  nativeImageEvidence,
  collectVerbAdoption,
  classifyRawEffect,
  extractAvailableSkills,
  findBatchSetParmOpportunities,
  findQueryMutationSteps,
  findSuppressedCookFailures,
  frameFromPath,
  isMutatingRawMethodName,
  parseLedgerArgs,
  parseVerbLedgerLine,
  qualityLoopRisks,
  renderOutputsFromPreview,
  requestedGoalReportedUnverified,
} from '../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';
const nativeImages=nativeImageEvidence([{index:7,canonical:{imageAttachments:[
  {from:'$HIP/render/a.png',attachment:{attachmentId:'native-a'}},
  {from:'$HIP/render/b.png',error:'route unavailable'},
]}}]);
assert.equal(nativeImages[0].delivered,true);assert.equal(nativeImages[0].semanticStatus,'unverified');
assert.equal(nativeImages[1].delivered,false);assert.equal(nativeImages[1].error,'route unavailable');

assert.equal(isMutatingRawMethodName('renderNode'), false);
const retainedRead=collectVerbAdoption([{isHoudini:true,tool:'houdini_query',args:{result_ref:'a'.repeat(64)},code:'',verbs:[]}]);
assert.equal(retainedRead.houdiniCalls,0);
assert.equal(retainedRead.hostResultDetailReads,1,'reading stored results is not a new HOM call');

const lines=Array.from({length:30},(_,i)=>`value_${i} = input_value_${i} + 100`).join('\n');
const retry=collectRetryWork([
  {index:1,tool:'houdini_exec',code:lines,failed:true,rollback:{applied:true},verbs:[{verb:'build_module',ok:true,ledgerIndex:1}]},
  {index:2,tool:'houdini_exec',code:lines.replace('input_value_15','corrected_value'),failed:false},
  {index:3,tool:'houdini_exec',code:'a completely unrelated long command'.repeat(32),failed:true},
]);
assert.equal(retry.candidates.length,1);
assert.deepEqual([retry.candidates[0].from,retry.candidates[0].to],[1,2]);
assert.ok(retry.candidates[0].changedLineExcerpts.added[0].line.includes('corrected_value'));
assert.equal(retry.appliedRollbackCalls,1);
assert.equal(retry.appliedRollbackCodeChars,lines.length);
assert.equal(retry.successfulBuildEntriesInAppliedRollbacks.length,1);
assert.equal(collectRetryWork([{index:1,tool:'houdini_exec',code:lines,failed:false},
  {index:2,tool:'houdini_exec',code:lines,failed:false}]).candidates.length,0,'successful repeated generation is not a failed retry');
assert.equal(collectRetryWork([{index:1,tool:'houdini_exec',code:'x'.repeat(70000),failed:true}]).similaritySkippedCalls[0],1);

for (const text of ['细致表现模型表面质感和近景结构', 'Use survey references and fine detail for close-up inspection']) {
  assert.equal(collectQualityLoopEvidence({userMessages:[{text}]}).applicable,true);
}
assert.equal(collectQualityLoopEvidence({userMessages:[{text:'把节点改名为OUT'}]}).applicable,false);
for (const tool of ['houdini_exec','houdini_query']) {
  const evidence = collectQualityLoopEvidence({steps:[{index:1,tool,failed:false,
    code:'# tangent direction\ng = n.geometry(); print(g.boundingBox())', resultText:'(0,0,0)-(1,1,1)',
    verbs:tool==='houdini_exec' ? [{verb:'set_parms',ok:true}] : []}]});
  assert.deepEqual(evidence.relations.probeSteps,[],'construction tangent comments are not relationship measurements');
}
const typedAdoption=collectVerbAdoption([
  {tool:'houdini_exec',isHoudini:true,args:{review:{parent:'/obj/g',output:'/obj/g/O'}},verbs:[],mutatingRawMethods:[]},
  {tool:'houdini_exec',isHoudini:true,args:{review_test:{tests:[]}},verbs:[],mutatingRawMethods:[]},
  {tool:'houdini_exec',isHoudini:true,args:{delivery:{action:'check'}},verbs:[],mutatingRawMethods:[]},
  {tool:'houdini_query',isHoudini:true,code:'__result__=hou.frame()',verbs:[],mutatingRawMethods:[]},
  {tool:'houdini_exec',isHoudini:true,code:'tab_create(...)',verbs:[{verb:'tab_create'}],mutatingRawMethods:[]},
]);
assert.equal(typedAdoption.structuredCalls,3);
assert.equal(typedAdoption.rawReadOnlyCalls,1);
assert.equal(typedAdoption.successfulExecVerbCoveragePct,100);
assert.equal(isMutatingRawMethodName('displayNode'), false);
assert.equal(isMutatingRawMethodName('render'), true);

assert.deepEqual(parseLedgerArgs('["/obj/a","tx",1]'), {
  positional: ['/obj/a', 'tx', 1], kwargs: {},
});
assert.deepEqual(parseLedgerArgs('["/obj/a"], {"frame": 12, "framing_frame": 20}'), {
  positional: ['/obj/a'], kwargs: { frame: 12, framing_frame: 20 },
});
assert.deepEqual(parseVerbLedgerLine(
  '1. [ok] verb_help(["set_keyframes"]) -> {"name":"set_keyframes","signature":"(node, channels: \'dict\', replace: \'bool\' = True) -> \'dict\'","doc":"x"} (0ms)',
), {
  ledgerIndex: 1,
  ok: true,
  verb: 'verb_help',
  args: '["set_keyframes"]',
  result: '{"name":"set_keyframes","signature":"(node, channels: \'dict\', replace: \'bool\' = True) -> \'dict\'","doc":"x"}',
  ms: 0,
});
assert.deepEqual(parseVerbLedgerLine(
  '2. [ok] set_parm(["/obj/a","label",") -> still arg"]) -> {"ok":true} (1.5ms)',
), {
  ledgerIndex: 2,
  ok: true,
  verb: 'set_parm',
  args: '["/obj/a","label",") -> still arg"]',
  result: '{"ok":true}',
  ms: 1.5,
});
assert.equal(parseVerbLedgerLine('not a ledger line'), null);
assert.equal(frameFromPath('E:/tmp/dsh_view_123_f25p5.png'), 25.5);
assert.equal(frameFromPath('E:/tmp/no_frame.png'), null);
assert.deepEqual(extractAvailableSkills(`
<available_skills>
- \`houdini-rig-animation-workflow\`: Rig work.
- \`houdini-trace-analysis\`: Trace work.
</available_skills>`), [
  'houdini-rig-animation-workflow', 'houdini-trace-analysis',
]);

const scattered = [{
  index: 7,
  time: 100,
  verbs: [
    ['a', 'x'], ['a', 'y'], ['b', 'x'], ['b', 'y'],
    ['c', 'x'], ['c', 'y'], ['d', 'x'], ['d', 'y'],
  ].map(([node, parm]) => ({ verb: 'set_parm', args: JSON.stringify([`/obj/${node}`, parm, 1]) })),
}];
assert.deepEqual(findBatchSetParmOpportunities(scattered), []);

const sameNode = [{
  index: 8,
  time: 200,
  verbs: [
    { verb: 'set_parms', args: JSON.stringify(['/obj/a', { tx: 1 }]) },
    ...['tx', 'ty', 'tz', 'rx'].map((parm) => ({
      verb: 'set_parm', args: JSON.stringify(['/obj/a', parm, 1]),
    })),
  ],
}];
assert.deepEqual(findBatchSetParmOpportunities(sameNode), [{
  index: 8,
  time: 200,
  node: '/obj/a',
  count: 3,
  parms: ['rx', 'ty', 'tz'],
}]);

const repeatedSameParm = [{
  index: 9,
  time: 300,
  verbs: [1, 2, 3].map((value) => ({
    verb: 'set_parm', args: JSON.stringify(['/obj/a', 'tx', value]),
  })),
}];
assert.deepEqual(findBatchSetParmOpportunities(repeatedSameParm), []);

assert.deepEqual(findSuppressedCookFailures([
  {
    index: 10, time: 400, tool: 'houdini_exec', isHoudini: true, failed: false,
    resultPreview: 'Executed successfully.\n\nstdout:\nBASE cook FAILED: Error while cooking.',
  },
  {
    index: 11, time: 500, tool: 'houdini_exec', isHoudini: true, failed: true,
    resultPreview: 'Execution failed: Error while cooking.',
  },
  {
    index: 12, time: 600, tool: 'houdini_exec', isHoudini: true, failed: false,
    resultPreview: 'Executed successfully.\n\nstdout:\ncook OK',
  },
]), [{
  index: 10,
  time: 400,
  tool: 'houdini_exec',
  resultPreview: 'Executed successfully.\n\nstdout:\nBASE cook FAILED: Error while cooking.',
}]);

const coverage = collectValidationCoverage([
  {
    index: 1, time: 1, tool: 'houdini_query', args: {}, verbs: [{
      verb: 'geo_frame_diff', ok: true, args: '["/obj/a/OUT",25,31]', result: {},
    }],
  },
  {
    index: 2, time: 2, tool: 'houdini_exec', args: {}, verbs: [{
      verb: 'render_view', ok: true,
      args: '["/obj/a/OUT"], {"frame": 31, "framing_frame": 31}',
      result: { output: 'E:/tmp/dsh_view_1_f31p0.png' },
    }],
  },
  {
    index: 3, time: 3, tool: 'houdini_exec', args: {}, verbs: [{
      verb: 'render_check', ok: true,
      args: '["E:/tmp/dsh_view_1_f31p0.png"], {"ref":"E:/tmp/dsh_view_0_f25p0.png"}',
      result: {},
    }],
  },
  {
    index: 4, time: 4, tool: 'vision_glance', verbs: [],
    args: { images: ['E:/tmp/dsh_view_0_f25p0.png', 'E:/tmp/dsh_view_1_f31p0.png'] },
  },
  {
    index: 5, time: 5, tool: 'read_image', failed: true, verbs: [],
    args: { path: 'E:/tmp/dsh_view_2_f40p0.png' },
  },
]);
assert.deepEqual(coverage.frames.geometry, [25, 31]);
assert.deepEqual(coverage.frames.render, [31]);
assert.deepEqual(coverage.frames.framing, [31]);
assert.deepEqual(coverage.frames.comparison, [25, 31]);
assert.deepEqual(coverage.frames.vision, [25, 31, 40]);
assert.deepEqual(coverage.frames.visionInspection, [25, 31, 40]);
assert.deepEqual(coverage.frames.all, [25, 31, 40]);
assert.equal(coverage.vision[1].ok, false);

const recovered = execResultFromPreview([
  'Executed successfully.',
  '',
  '__result__:',
  '{"output":"E:/tmp/dsh_view_9_f52p0.png","frame":52,"framing":{"frame":1}}',
  '',
  'verbs (1):',
  '1. [ok] render_view(["/obj/a/OUT"], {"frame":52}) -> {"output":"E:/tmp/dsh_view_9_f52p0.png"鈥 (10ms)',
].join('\n'));
assert.equal(recovered.output, 'E:/tmp/dsh_view_9_f52p0.png');
assert.deepEqual(renderOutputsFromPreview(
  'stdout: {"output":"E:/tmp/a_f1p0.png"} then {"output":"E:/tmp/a_f21p0.png"} and {"output":"E:/tmp/a_f1p0.png"}',
), ['E:/tmp/a_f1p0.png', 'E:/tmp/a_f21p0.png']);

const recoveredCoverage = collectValidationCoverage([{
  index: 6,
  time: 6,
  tool: 'houdini_exec',
  resultPreview: 'Executed successfully.\n\n__result__:\n{"output":"E:/tmp/dsh_view_9_f52p0.png","frame":52,"framing":{"frame":1}}\n\nverbs (1):',
  verbs: [{
    verb: 'render_view', ok: true,
    args: '["/obj/a/OUT"], {"frame":52,"framing_frame":1}',
    result: '{"output":"E:/tmp/dsh_view_9_f52p0.png"鈥',
  }],
}, {
  index: 7,
  time: 7,
  tool: 'houdini_exec',
  resultPreview: 'Executed successfully.\n\n__result__:\n{"path":"E:/tmp/dsh_view_9_f52p0.png","size":[1280,720],"content_bbox":[186,0,1119,717]}\n\nverbs (1):',
  verbs: [{ verb: 'render_check', ok: true, args: '["E:/tmp/dsh_view_9_f52p0.png"]', result: '{}' }],
}]);
assert.equal(recoveredCoverage.renders[0].output, 'E:/tmp/dsh_view_9_f52p0.png');
assert.equal(recoveredCoverage.renders[0].frame, 52);
assert.equal(recoveredCoverage.renders[0].framing_frame, 1);
assert.equal(recoveredCoverage.comparisons[0].touches_edge, true);

const bootstrapFailure = classifyVisionEvidence({
  tool: 'vision_bootstrap', failed: false, args: { paths: ['E:/tmp/a_f1p0.png'] },
  resultPreview: '{"ok":false,"code":"STRUCTURED_BOOTSTRAP_DISABLED"}',
});
assert.equal(bootstrapFailure.role, 'setup');
assert.equal(bootstrapFailure.ok, false);
assert.equal(bootstrapFailure.reason, 'STRUCTURED_BOOTSTRAP_DISABLED');

const describeRefusal = classifyVisionEvidence({
  tool: 'vision_glance', failed: false, args: { images: ['E:/tmp/a_f13p0.png'] },
  resultPreview: '由于我无法查看图像（模型仅接受文本输入，且图片已被省略），无法分析。',
});
assert.equal(describeRefusal.role, 'inspection');
assert.equal(describeRefusal.semanticOk, false);
assert.equal(describeRefusal.reason, 'textual_image_access_refusal');

const presentation = classifyVisionEvidence({
  tool: 'vision_present', failed: false, args: { image: 'E:/tmp/a_f13p0.png' }, resultPreview: '{}',
});
assert.equal(presentation.role, 'presentation');
assert.equal(presentation.semanticOk, null);

const readImageFilePath = classifyVisionEvidence({
  tool: 'read_image', failed: false, args: { file_path: 'E:/tmp/a_f21p0.png' }, resultPreview: '<type>image</type>',
});
assert.deepEqual(readImageFilePath.images, ['E:/tmp/a_f21p0.png']);
assert.deepEqual(readImageFilePath.frames, [21]);

const pixelDiff = classifyVisionEvidence({
  tool: 'vision_pixel_diff', failed: false,
  args: { original: 'E:/tmp/a.png', rebuilt: 'E:/tmp/b.png' },
  resultPreview: '{"overallDifferencePct":8.05}',
});
assert.equal(pixelDiff.role, 'pixel');
assert.equal(pixelDiff.semanticOk, null);
assert.equal(pixelDiff.ok, true);

assert.deepEqual(collectVerbAdoption([
  { tool: 'houdini_exec', isHoudini: true, failed: false, verbs: [{ verb: 'tab_create' }], mutatingRawMethods: [] },
  { tool: 'houdini_query', isHoudini: true, failed: false, verbs: [], mutatingRawMethods: [] },
  { tool: 'houdini_exec', isHoudini: true, failed: true, verbs: [], mutatingRawMethods: ['cook'], resultPreview: 'raw-hou gate: blocked BEFORE execution' },
]), {
  houdiniCalls: 3,
  hostResultDetailReads: 0,
  callsWithVerbs: 1,
  callCoveragePct: 33.3,
  verbCalls: 1,
  verbDensity: 0.33,
  rawReadOnlyCalls: 1,
  rawSuspectedEffectCalls: 0,
  rawUnknownEffectCalls: 0,
  rawFailedCalls: 0,
  execCalls: 2,
  successfulExecCalls: 1,
  successfulExecWithVerbs: 1,
  successfulExecVerbCoveragePct: 100,
  blockedVerblessRawMutationCalls: 1,
  successfulVerblessRawMutationCalls: 0,
});

assert.deepEqual(findQueryMutationSteps([
  { index: 1, time: 1, tool: 'houdini_query', verbs: [{ verb: 'scene_info' }], mutatingRawMethods: [] },
  { index: 2, time: 2, tool: 'houdini_query', verbs: [{ verb: 'set_timeline' }, { verb: 'cook_node' }], mutatingRawMethods: [] },
  { index: 3, time: 3, tool: 'houdini_query', verbs: [], mutatingRawMethods: ['pressButton'] },
]), [{
  index: 2,
  time: 2,
  tool: 'houdini_query',
  codePreview: undefined,
  mutatingRawMethods: [],
  mutatingVerbs: ['set_timeline', 'cook_node'],
}, {
  index: 3,
  time: 3,
  tool: 'houdini_query',
  codePreview: undefined,
  mutatingRawMethods: ['pressButton'],
  mutatingVerbs: [],
}]);

const incompleteQualityLoop = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '请做一个细节丰富的程序化自行车。' }],
  assistantMessages: [{
    time: 2,
    text: '目标是山地车；无外部参考，按典型尺寸假设。暴露控制参数，并检查连接关系和整体渲染证据。',
  }, {
    time: 20,
    text: '完成：20 点 / 10 prim，视觉验证通过。',
  }],
  availableTools: ['web_search', 'read'],
  activatedSkills: ['houdini-sop-workflow'],
  steps: [{
    index: 1, time: 3, tool: 'skill', failed: false, args: { name: 'houdini-sop-workflow' },
    resultPreview: 'Load referenced resources only as needed: procedural-quality-contract.md', verbs: [],
  }, {
    index: 2, time: 4, tool: 'houdini_exec', failed: false, verbs: Array.from({ length: 25 }, (_, index) => ({
      verb: 'tab_create', ok: true, args: JSON.stringify(['/obj/bike', 'null', `n${index}`]),
    })),
  }, {
    index: 3, time: 5, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'render_view', ok: true, args: '["/obj/bike/OUT"]', result: { output: 'E:/tmp/bike_f1p0.png' },
    }], resultText: '{"points":25,"prims":12}',
  }],
});
assert.equal(incompleteQualityLoop.applicable, true);
assert.deepEqual(incompleteQualityLoop.contract.missing, ['simplifications']);
assert.equal(incompleteQualityLoop.reference.qualityContractRequired, true);
assert.deepEqual(incompleteQualityLoop.reference.qualityContractLoadSteps, []);
assert.equal(incompleteQualityLoop.reference.unsupportedExternalTruthClaims.length, 0);
assert.equal(incompleteQualityLoop.skeleton.tabCreatesBeforeFirstRender, 25);
assert.deepEqual(incompleteQualityLoop.perturbation.restored, []);
assert.equal(incompleteQualityLoop.freshness.finalCountMatchesEvidence, false);
assert.deepEqual(qualityLoopRisks(incompleteQualityLoop).map((risk) => risk.code), [
  'quality_contract_incomplete',
  'quality_contract_reference_not_loaded',
  'external_reference_available_but_unused',
  'late_first_visual_validation',
  'procedural_control_not_perturbed',
  'relationship_contract_without_evidence',
  'stale_final_geometry_counts',
]);

const completeQualityLoop = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: 'Create a detailed procedural product asset.' }],
  assistantMessages: [{
    time: 2,
    text: 'Target and deliverable: product-level LOD from a sourced reference. Simplifications: omit internals. Units and dimensions are in meters. Expose controls. Validate axis clearance relations with query evidence and local render views.',
  }, {
    time: 20,
    text: 'Final output: 100 points / 50 prims; remaining external claims are unverified.',
  }],
  availableTools: ['web_search', 'read'],
  activatedSkills: ['houdini-sop-workflow'],
  steps: [{ index: 1, time: 2.1, tool: 'web_search', failed: false, args: {}, verbs: [] }, {
    index: 2, time: 2.2, tool: 'read', failed: false, args: {}, verbs: [],
    resultPreview: '# 程序化 SOP 质量合同',
  }, {
    index: 3, time: 3, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'set_parms', ok: true, args: '["/obj/product",{"scale":1}]',
    }],
  }, {
    index: 4, time: 4, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'set_parms', ok: true, args: '["/obj/product",{"scale":1.2}]',
    }, { verb: 'cook_node', ok: true, args: '["/obj/product/OUT"]' }],
  }, {
    index: 5, time: 5, tool: 'houdini_query', failed: false,
    code: 'print("clearance", node.geometry().boundingBox())', resultText: 'clearance 0.01', verbs: [],
  }, {
    index: 6, time: 6, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'set_parms', ok: true, args: '["/obj/product",{"scale":1}]',
    }, { verb: 'cook_node', ok: true, args: '["/obj/product/OUT"]' }],
  }, {
    index: 7, time: 7, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'render_view', ok: true, args: '["/obj/product/OUT"]', result: { output: 'E:/tmp/product_f1p0.png' },
    }], resultText: '{"points":100,"prims":50}',
  }],
});
assert.deepEqual(completeQualityLoop.contract.missing, []);
assert.deepEqual(completeQualityLoop.reference.researchSteps, [1]);
assert.deepEqual(completeQualityLoop.reference.qualityContractLoadSteps, [2]);
assert.equal(completeQualityLoop.perturbation.restored.length, 1);
assert.deepEqual(completeQualityLoop.relations.probeSteps, [5]);
assert.equal(completeQualityLoop.freshness.finalCountMatchesEvidence, true);
assert.deepEqual(qualityLoopRisks(completeQualityLoop), []);

const cinematicEffectQualityLoop = collectQualityLoopEvidence({
  userMessages: [{
    time: 1,
    text: '请制作一个有电影感、可以调节的沙尘冲击效果，并给出可靠的验证结果。',
  }],
  assistantMessages: [{
    time: 2,
    text: '目标是中远景镜头级轮廓；无外部参考。暴露全部可调参数，并用关键帧 render 与动画数据验证。',
  }, {
    time: 20,
    text: '完成。\n| 电影感（颜色/光影/体积光） | **unverified** | 仍需正式材质与灯光 |',
  }],
  activatedSkills: ['houdini-sop-workflow'],
  steps: [{
    index: 1, time: 3, tool: 'read', failed: false, verbs: [],
    resultPreview: '# 程序化 SOP 质量合同',
  }, {
    index: 2, time: 4, tool: 'houdini_exec', failed: false,
    verbs: [{ verb: 'tab_create', ok: true, args: '["/obj","geo","dust"]' }],
  }],
});
assert.equal(cinematicEffectQualityLoop.applicable, true);
assert.equal(cinematicEffectQualityLoop.contract.requirements.controls, true);
assert.deepEqual(cinematicEffectQualityLoop.contract.missing, ['simplifications']);
assert.deepEqual(cinematicEffectQualityLoop.reference.qualityContractLoadSteps, [1]);
assert.deepEqual(requestedGoalReportedUnverified(
  [{ text: '请制作一个有电影感、可以调节的沙尘冲击效果。' }],
  [{ text: '完成。\n| 电影感（颜色/光影） | unverified |' }],
), [{
  signal: 'cinematic',
  line: '| 电影感（颜色/光影） | unverified |',
}]);
assert.deepEqual(requestedGoalReportedUnverified(
  [{ text: '请制作一个有电影感的效果。' }],
  [{ text: '部分完成；电影感仍为 unverified。' }],
), []);

const userReferenceBoundary = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '按这个参考链接做细节丰富的程序化产品：https://example.test/spec' }],
  assistantMessages: [{ time: 2, text: '目标符合该真实产品规格；产品级 LOD，不省略外壳，使用米制控制参数，验证连接关系并渲染取证。' }],
  availableTools: ['web_search'],
  steps: [],
});
assert.equal(userReferenceBoundary.reference.userProvidedReference, true);
assert.equal(
  qualityLoopRisks(userReferenceBoundary).some((risk) => risk.code === 'external_reference_available_but_unused'),
  false,
);

const delegatedStyleBoundary = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '做一个高质量的风格化模型，不需要外部参考，比例你决定。' }],
  assistantMessages: [{ time: 2, text: '采用典型比例作为未验证的风格假设。' }],
  availableTools: ['web_search'],
  steps: [],
});
assert.equal(delegatedStyleBoundary.reference.userAuthorizedNoResearch, true);
assert.equal(
  qualityLoopRisks(delegatedStyleBoundary).some((risk) => risk.code === 'external_reference_available_but_unused'),
  false,
);

const spareParmPerturbation = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '做一个高质量程序化资产。' }],
  assistantMessages: [{ time: 2, text: '产品级 LOD；无参考假设；不省略；暴露控制参数，验证关系并渲染。' }],
  steps: [{ index: 1, time: 3, tool: 'houdini_exec', failed: false, verbs: [{
    verb: 'create_spare_parms', ok: true,
    args: '["/obj/asset/CONTROLS"], {"spec":[{"type":"float","name":"scale","default":1}]}',
    result: { leaf_values: { scale: 1 } },
  }] }, {
    index: 2, time: 4, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'set_parm', ok: true, args: '["/obj/asset/CONTROLS","scale",1.25]',
    }, { verb: 'cook_node', ok: true, args: '["/obj/asset/OUT"]' }],
  }, {
    index: 3, time: 5, tool: 'houdini_query', failed: false, code: 'measure clearance distance', verbs: [],
  }, {
    index: 4, time: 6, tool: 'houdini_exec', failed: false, verbs: [{
      verb: 'set_parm', ok: true, args: '["/obj/asset/CONTROLS","scale",1]',
    }, { verb: 'cook_node', ok: true, args: '["/obj/asset/OUT"]' }],
  }],
});
assert.equal(spareParmPerturbation.perturbation.restored.length, 1);
assert.equal(spareParmPerturbation.perturbation.restored[0].node, '/obj/asset/CONTROLS');

const structuredContract = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '请做一个细节丰富的程序化自行车。' }],
  assistantMessages: [{ time: 2, text: '开始建立任务合同。' }],
  steps: [{
    index: 1, time: 2.1, tool: 'todo_write', failed: false,
    args: { todos: [{ content: '调研真实来源与假设', status: 'in_progress' }] }, verbs: [],
  }, {
    index: 2, time: 2.2, tool: 'create_goal', failed: false,
    args: { objective: '目标是山地车，暴露控制参数；逐项验证同轴、间隙关系，并交付整体与局部特写证据。' },
    verbs: [],
  }, {
    index: 3, time: 3, tool: 'houdini_exec', failed: false,
    verbs: [{ verb: 'tab_create', ok: true, args: '["/obj","geo","bike"]' }],
  }],
});
assert.equal(structuredContract.contract.fields.referenceStatus, true);
assert.equal(structuredContract.contract.fields.relations, true);
assert.equal(structuredContract.contract.fields.evidencePlan, true);
assert.deepEqual(structuredContract.contract.missing, ['simplifications']);

const reverseSkeletonWording = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '做一个高质量程序化资产。' }],
  assistantMessages: [{ time: 4, text: '锚点已经创建，接下来数值验证骨架并确认通过。' }],
  steps: [{
    index: 1, time: 5, tool: 'houdini_exec', failed: false,
    verbs: Array.from({ length: 25 }, (_, index) => ({
      verb: 'tab_create', ok: true, args: JSON.stringify(['/obj/a', 'null', `n${index}`]),
    })),
  }, {
    index: 2, time: 6, tool: 'houdini_exec', failed: false,
    verbs: [{ verb: 'render_view', ok: true, args: '["/obj/a/OUT"]', result: {} }],
  }],
});
assert.equal(reverseSkeletonWording.skeleton.checkpointMentions.length, 1);
assert.equal(
  qualityLoopRisks(reverseSkeletonWording).some((risk) => risk.code === 'late_first_visual_validation'),
  false,
);

const commaCountFreshness = collectQualityLoopEvidence({
  userMessages: [{ time: 1, text: '做一个高质量程序化资产。' }],
  assistantMessages: [{ time: 4, text: '最终输出为 14,189 点 / 12,510 面。' }],
  steps: [{
    index: 1, time: 3, tool: 'houdini_exec', failed: false,
    verbs: [{ verb: 'set_parm', ok: true, args: '["/obj/a/CONTROLS","scale",1]' }],
    resultPreview: 'FINAL: pts 14189 prims 12510',
  }],
});
assert.deepEqual(commaCountFreshness.freshness.latestGeometryCounts, {
  index: 1, points: 14189, prims: 12510,
});
assert.deepEqual(commaCountFreshness.freshness.finalGeometryCountClaim, {
  points: 14189, prims: 12510,
});
assert.equal(commaCountFreshness.freshness.finalCountMatchesEvidence, true);

assert.equal(completedVisionTodoWithoutEvidence([
  { content: '视觉检查', status: 'completed' },
]), true);
assert.equal(completedVisionTodoWithoutEvidence([
  { content: '视觉服务凭据失效，语义检查标记 unverified', status: 'completed' },
]), false);
assert.equal(completedVisionTodoWithoutEvidence([
  { content: '视觉检查', status: 'completed' },
], [{ semanticOk: true }]), false);

// Only selected options are contract facts, never unselected UI suggestions.
const selectedContract = collectQualityLoopEvidence({
  userMessages: [{time: 1, text: '创建程序化资产'}],
  steps: [{index: 1, time: 2, tool: 'ask_user_question', args: {questions: [
    {id: 'quality', header: 'LOD', options: [
      {label: '产品级', description: '不省略细节，需验证控制参数和连接关系'},
      {label: '预览', description: '无参考假设'},
    ]},
  ]}, resultText: JSON.stringify({answers: [{id: 'quality', selected: ['产品级']}]}), verbs: []},
  {index: 2, time: 3, tool: 'houdini_exec', verbs: [{verb: 'tab_create', ok: true}],
   code: 'n = tab_create(parent, "null"); g = n.geometry(); print("clearance", g.boundingBox())', resultText:'clearance 0.01'},
  {index: 3, time: 4, tool: 'houdini_exec', verbs: [{verb: 'render_view', ok: true, args: '["/obj/a/SKELETON"]'}]},
  ],
});
assert.equal(selectedContract.contract.fields.qualityLod, true);
assert.equal(selectedContract.contract.fields.simplifications, true);
assert.equal(selectedContract.contract.fields.referenceStatus, false, 'unselected assumptions must not enter contract');
assert.deepEqual(selectedContract.relations.probeSteps, [2]);
assert.equal(selectedContract.skeleton.checkpointMentions[0].source, 'render_target');
assert.equal(findQueryMutationSteps([{tool: 'houdini_query', verbs: [{verb: 'verify_network', ok: true}]}]).length, 1);
const fullStep = {index: 1, time: 2, tool: 'houdini_query', verbs: [], code: 'print("clearance", node.geometry().boundingBox())', resultText: 'clearance 0.01'};
const compactStep = {...fullStep};
Object.defineProperty(compactStep, 'code', {value: fullStep.code, enumerable: false});
Object.defineProperty(compactStep, 'resultText', {value: fullStep.resultText, enumerable: false});
assert.deepEqual(collectQualityLoopEvidence({steps: [compactStep]}), collectQualityLoopEvidence({steps: [fullStep]}));
console.log('trace evidence helper tests passed');

// H-06: selected facts/custom answers, never the unchosen LOD or header alone.
const intake={index:1,time:1,tool:'ask_user_question',args:{questions:[{id:'detail',header:'LOD',options:[
  {label:'高细节',description:'近景使用'}, {label:'预览',description:'省略细节，假设尺寸'}]}]},
  resultText:JSON.stringify({answers:[{id:'detail',selected:['高细节']}]}),verbs:[]};
const initialBuild={index:2,time:2,tool:'houdini_exec',verbs:[{verb:'tab_create',ok:true}]};
const fromChoice=collectQualityLoopEvidence({userMessages:[{time:0,text:'创建一个模型'}],steps:[intake,initialBuild]});
assert.equal(fromChoice.contract.fields.qualityLod,true);
assert.equal(fromChoice.applicable,true,'selected high detail activates quality audit even for a short initial request');
assert.equal(fromChoice.contract.fields.simplifications,false);
assert.equal(fromChoice.contract.clarifications[0].question_id,'detail');
const decide={...intake,resultText:JSON.stringify({answers:[{id:'detail',selected:[],custom:'你决定'}]})};
assert.equal(collectQualityLoopEvidence({steps:[decide,initialBuild]}).contract.fields.qualityLod,false,'LOD header is a question, not a chosen quality');
const custom={...intake,resultText:JSON.stringify({answers:[{id:'detail',selected:[],custom:'需要近景细节'}]})};
assert.equal(collectQualityLoopEvidence({steps:[custom,initialBuild]}).contract.fields.qualityLod,true);
assert.equal(collectQualityLoopEvidence({steps:[{...custom,failed:true},initialBuild]}).contract.fields.qualityLod,false);
assert.equal(collectQualityLoopEvidence({steps:[{...intake,resultText:JSON.stringify({answers:[{id:'wrong',selected:['高细节']}]})},initialBuild]}).contract.fields.qualityLod,false);
const late={...custom,index:3,time:3};
const lateEvidence=collectQualityLoopEvidence({steps:[initialBuild,late]});
assert.equal(lateEvidence.contract.fields.qualityLod,false);
assert.equal(lateEvidence.contract.clarifications.length,1,'late change retained without backdating initial contract');

const measured={index:3,time:3,tool:'houdini_query',failed:false,verbs:[],
  code:'g = node.geometry()\na = g.points()[0].position()\nmetrics = {"axis_gap": a[0]}\n__result__ = metrics',
  resultText:'Executed successfully.\n\n__result__:\n{"axis_gap":0.02}'};
const measureEvidence=collectQualityLoopEvidence({steps:[measured]});
assert.deepEqual(measureEvidence.relations.probeSteps,[3]);
assert.match(measureEvidence.relations.candidates[0].scope,/not certified/);
assert.deepEqual(collectQualityLoopEvidence({steps:[{...measured,transaction:{status:'rolled_back'}}]}).relations.probeSteps,[]);
const commentOnly={...measured,code:'code = """// tangent\nnode.geometry(); print(1)"""\nset_parm(n,"snippet",code)',
  resultText:'stdout:\n[verb] set_parm tangent 1\n\nverbs (1):\n1. [ok] set_parm([]) -> {} (1ms)'};
assert.deepEqual(collectQualityLoopEvidence({steps:[commentOnly]}).relations.probeSteps,[]);
const literalClaim={...measured,code:'__result__={"clearance":0.02}'};
assert.deepEqual(collectQualityLoopEvidence({steps:[literalClaim]}).relations.probeSteps,[],'a literal reported number without geometry access is not a measured probe');
assert.deepEqual(collectQualityLoopEvidence({steps:[{...literalClaim,code:'text="node.geometry()"\n__result__={"clearance":0.02} # another.geometry()'}]}).relations.probeSteps,[],'quoted or commented geometry calls do not count as execution');
const sourceDump={...measured,resultText:'Executed successfully.\n\n__result__:\n'+JSON.stringify({parms:[{name:'snippet',value:'// tangent 10; clearance=1'}],points:100})};
assert.deepEqual(collectQualityLoopEvidence({steps:[sourceDump]}).relations.probeSteps,[],'source text in parameter readback is not a measured relation');

const render={index:1,time:1,tool:'houdini_exec',verbs:[{verb:'render_view',ok:true,args:'["/obj/item/OUT"], {"direction":"front"}',result:{output:'C:/render/front.png',frame:1}}],
  canonical:{media:[{from:'C:/render/front.png',to:'E:/workspace/hash-front.png'}]}};
const inspect={index:2,time:2,tool:'read_image',args:{path:'E:/workspace/hash-front.png'},resultText:'image loaded',verbs:[]};
const edit={index:3,time:3,tool:'houdini_exec',verbs:[{verb:'set_parm',ok:true,args:'["/obj/item/CTRL","width",2]'}],
  canonical:{execution:{impact:{nodes:[{path:'/obj/item/OUT'}],attempted:true}}}};
const finalVisual=[{time:5,text:'完成，视觉检查通过。'}];
const stale=collectQualityLoopEvidence({steps:[render,inspect,edit],assistantMessages:finalVisual});
assert.equal(stale.freshness.visual.inspections[0].status,'stale_after_recorded_target_change');
const hiddenCanonical={...render};Object.defineProperty(hiddenCanonical,'canonical',{value:render.canonical,enumerable:false});
assert.deepEqual(collectQualityLoopEvidence({steps:[hiddenCanonical,inspect,edit]}),collectQualityLoopEvidence({steps:[render,inspect,edit]}),'compact extraction retains canonical relay/impact facts during analysis');
const legacyRender={...render,canonical:undefined,resultText:'media (relayed):\n- C:/render/front.png -> E:/workspace/hash-front.png (12 KB)'};
assert.equal(collectQualityLoopEvidence({steps:[legacyRender,inspect]}).freshness.visual.inspections[0].productionIndex,1);
assert.equal(collectQualityLoopEvidence({steps:[legacyRender,{...inspect,args:{path:'E:/other/hash-front.png'}}]}).freshness.visual.inspections[0].status,'unlinked_image','same basename does not establish media provenance');
assert.ok(qualityLoopRisks(stale).some(r=>r.code==='visual_completion_claim_with_stale_evidence'));
const reread={...inspect,index:4,time:4};
assert.equal(collectQualityLoopEvidence({steps:[render,edit,reread]}).freshness.visual.inspections[0].status,'stale_after_recorded_target_change','reading an old image later does not refresh it');
const newRender={...render,index:4,time:4},newRead={...inspect,index:5,time:5};
const refreshed=collectQualityLoopEvidence({steps:[render,inspect,edit,newRender,newRead],assistantMessages:finalVisual});
assert.equal(refreshed.freshness.visual.latestInspections[0].status,'no_recorded_change');
assert.ok(!qualityLoopRisks(refreshed).some(r=>r.code==='visual_completion_claim_with_stale_evidence'));
const failedRead={...inspect,failed:true};
assert.equal(collectQualityLoopEvidence({steps:[render,failedRead]}).freshness.visual.inspections[0].status,'inspection_access_failed');
assert.equal(collectQualityLoopEvidence({steps:[{...inspect,args:{path:'external-reference.png'}}]}).freshness.visual.inspections[0].status,'unlinked_image');
assert.equal(collectQualityLoopEvidence({steps:[render,inspect,{index:3,tool:'houdini_exec',verbs:[{verb:'scene_save',ok:true}]}]}).freshness.visual.inspections[0].status,'no_recorded_change','saving alone does not change rendered geometry');
const unknownFailure={index:3,tool:'houdini_exec',failed:true,transaction:{status:'recovery_unverified'},verbs:[]};
assert.equal(collectQualityLoopEvidence({steps:[render,inspect,unknownFailure]}).freshness.visual.inspections[0].status,'freshness_unverified_after_failed_execution');

const failedCheckpoint={index:1,tool:'houdini_exec',failed:false,verbs:[{verb:'verify_network',ok:true,
  result:{output:'/obj/a/OUT',scope:'direct_children',ok:false,nonempty:false}}]};
const succeededCheckpoint={index:2,tool:'houdini_exec',failed:false,verbs:[{verb:'verify_network',ok:true,
  result:{output:'/obj/a/OUT',scope:'direct_children',ok:true,nonempty:true}}]};
assert.ok(qualityLoopRisks(collectQualityLoopEvidence({steps:[failedCheckpoint]})).some(r=>r.code==='unresolved_output_checkpoints'));
assert.ok(!qualityLoopRisks(collectQualityLoopEvidence({steps:[failedCheckpoint,succeededCheckpoint]})).some(r=>r.code==='unresolved_output_checkpoints'));
const assumptions=collectQualityLoopEvidence({assistantMessages:[{text:'符合真实类别，但具体数值是典型值的假设，而非已核实规格。'}]});
assert.equal(assumptions.reference.unsupportedExternalTruthClaims.length,0);
const builtCheckpoint={index:1,tool:'houdini_exec',failed:false,verbs:[{verb:'build_module',ok:true,
  result:{validation:{output:'/obj/a/OUT',scope:'explicit_nodes',ok:true,nonempty:true},interface_checks:{ok:true}}}]};
const controlCheckpoint={index:2,tool:'houdini_exec',failed:false,verbs:[{verb:'test_controls',ok:true,
  result:{ok:true,restored:true,output:'/obj/a/OUT',results:[{id:'length',status:'pass'}]}}]};
const quality=collectQualityLoopEvidence({steps:[builtCheckpoint,controlCheckpoint],
  userMessages:[{text:'做一个程序化资产'}],assistantMessages:[{text:'假设的镜头级模型，有控制参数与关系验证，不做隐藏细节。'}]});
assert.equal(quality.outputCheckpoints.length,1);
assert.equal(collectQualityLoopEvidence({steps:[{...builtCheckpoint,transaction:{status:'rolled_back'}}]}).outputCheckpoints.length,0,
  'a successful build later rolled back is not current output evidence');
assert.deepEqual(quality.relations.probeSteps,[1]);
assert.equal(quality.perturbation.controlTests.length,1);
assert.ok(!qualityLoopRisks(quality).some(r=>r.code==='procedural_control_not_perturbed'));
assert.equal(findQueryMutationSteps([{tool:'houdini_query',verbs:[{verb:'test_controls',ok:true}]}]).length,1);

assert.deepEqual(collectQualityLoopEvidence({steps:[{...measured,transaction:{status:'recovery_unverified'}}]}).relations.probeSteps,[],
  'unverified recovery cannot contribute retained measurement evidence');
const failedReread={...inspect,index:4,time:4,failed:true};
assert.ok(qualityLoopRisks(collectQualityLoopEvidence({steps:[render,inspect,edit,failedReread],assistantMessages:finalVisual}))
  .some(r=>r.code==='visual_completion_claim_with_stale_evidence'),
  'a failed reread must not hide the prior successful but stale inspection');

const sourcePage=(index,ref,text,offset=0,total=text.length)=>({index,tool:'houdini_query',args:{source_ref:ref},
  canonical:{ok:true,result:{source_ref:ref,format:'json_text_page',text,offset,total_chars:total,
    next_offset:offset+text.length<total?offset+text.length:null}}});
const discovery=sourcePage(1,'index','[{"source_ref":"'+'a'.repeat(64)+'"}]');
assert.equal(collectQualityLoopEvidence({steps:[discovery]}).manualReview.taskSources.discoveryWithoutBodyReadObserved,true);
const partialSource=sourcePage(2,'a'.repeat(64),'partial',0,100);
const sourceReview=collectQualityLoopEvidence({steps:[discovery,partialSource]}).manualReview.taskSources;
assert.equal(sourceReview.discoveryWithoutBodyReadObserved,false);
assert.equal(sourceReview.reads[1].next_offset,7);
assert.equal(sourceReview.reads[1].total_chars,100,'partial retrieval is visible and never reported as full consumption');
assert.equal(collectQualityLoopEvidence({steps:[discovery,{...partialSource,failed:true}]}).manualReview.taskSources.discoveryWithoutBodyReadObserved,true);
assert.equal(collectQualityLoopEvidence({steps:[{...discovery,canonical:undefined}]}).manualReview.taskSources.reads[0].status,'return_unverified');
for(const conclusion of ['右侧支架明显脱离主体。','右侧支架与主体接触，连接完整。','遮挡严重，无法确定支架是否连接。']) {
  const comparison=collectQualityLoopEvidence({steps:[render,{...inspect,tool:'vision_glance',resultText:conclusion}],
    assistantMessages:[{time:2.5,text:'读取了检查结果。'},...finalVisual]}).manualReview.visualComparison;
  assert.equal(comparison.inspections[0].toolResult.text,conclusion);
  assert.equal(comparison.finalStatement.text,finalVisual[0].text);
  assert.equal(comparison.verdict,'requires_semantic_review','semantic contradictions must remain explicit review material, not a lexical pass/fail');
}
