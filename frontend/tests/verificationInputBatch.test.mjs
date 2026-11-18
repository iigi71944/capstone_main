import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const dirname = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(path.join(dirname, '../lib/verificationInputSelection.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const loaded = { exports: {} };
new Function('module', 'exports', compiled)(loaded, loaded.exports);
const { parseVerificationInputs } = loaded.exports;
const row = (props = {}) => ({
  functionName: '', argsText: '[]', kwargsText: '{}', stdinText: '', ...props,
});

test('two separate stdin-only cases retain their order', () => {
  const selection = parseVerificationInputs([
    row({ stdinText: '민수\n85' }),
    row({ stdinText: '영희\n20' }),
  ]);
  assert.equal(selection.ok, true);
  assert.equal(selection.stdin, '민수\n85');
  assert.deepEqual(selection.stdinCases, ['민수\n85','영희\n20']);
  assert.equal(selection.functionCases, undefined);
});

test('eight stdin cases can be submitted', () => {
  const selection = parseVerificationInputs(Array.from({length: 8}, (_, i) => row({stdinText: `name${i}\n${i}`})));
  assert.equal(selection.ok, true);
  assert.equal(selection.stdinCases.length, 8);
});

test('unused blank tests do not create fictitious execution results', () => {
  const selection = parseVerificationInputs([row({stdinText:'A'}),row(),row()]);
  assert.deepEqual(selection.stdinCases,['A']);
});

test('unnamed stdin and named function both retained', () => {
  const selection = parseVerificationInputs([
    row({stdinText:'A'}),
    row({functionName:'calculate',argsText:'[5]',stdinText:'B'}),
  ]);
  assert.equal(selection.ok,true);
  assert.deepEqual(selection.stdinCases,['A','B']);
  assert.deepEqual(selection.functionCases,[{function:'calculate',args:[5],kwargs:{},stdin:'B'}]);
});

test('function-only requests retain historical behavior without batch inputs', () => {
  const selection = parseVerificationInputs([row({functionName:'f',argsText:'[4]'})]);
  assert.equal(selection.ok,true);
  assert.deepEqual(selection.stdinCases,[]);
  assert.equal(selection.stdin,undefined);
});

test('each stdin is byte-for-byte preserved including whitespace and newline', () => {
  const selection = parseVerificationInputs([row({stdinText:'  Jin \n 25\n'}),row({stdinText:'\n'})]);
  assert.equal(selection.ok,true);
  assert.deepEqual(selection.stdinCases,['  Jin \n 25\n','\n']);
});

test('more than eight rows is rejected before reaching backend', () => {
  const selection = parseVerificationInputs(Array.from({length:9},(_,i)=>row({stdinText:`${i}`})));
  assert.equal(selection.ok,false);
  assert.match(selection.error,/8/);
});

test('UI and request wiring reference batch result field', () => {
  const ui=readFileSync(path.join(dirname,'../components/sections/StyleApplySection.tsx'),'utf8');
  const api=readFileSync(path.join(dirname,'../lib/api.ts'),'utf8');
  assert.match(ui,/stdinCaseResults\.map\(\(test\) =>/);
  assert.match(ui,/result=\{test\.original\}/);
  assert.match(ui,/result=\{test\.transformed\}/);
  assert.match(api,/requestBody\.stdin_cases = stdinCases;/);
});
