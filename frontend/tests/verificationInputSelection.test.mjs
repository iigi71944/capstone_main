import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// Works with the project's Node 20 Docker image: use the installed TypeScript
// compiler to run this pure TS module without a new test dependency.
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

const blank = (values = {}) => ({
  functionName: '', argsText: '[]', kwargsText: '{}', stdinText: '', ...values,
});
const accepted = (drafts) => {
  const out = parseVerificationInputs(drafts);
  assert.equal(out.ok, true, out.ok ? '' : out.error);
  return out;
};
const rejected = (drafts, fragment) => {
  const out = parseVerificationInputs(drafts);
  assert.equal(out.ok, false);
  assert.ok(out.error.includes(fragment), out.error);
};

test('stdin only: two lines and no function name', () => {
  const x = accepted([blank({stdinText:'민수\n2'})]);
  assert.equal(x.stdin, '민수\n2');
  assert.equal(x.functionCases, undefined);
});
test('stdin only: trailing newline preserved', () => {
  assert.equal(accepted([blank({stdinText:'민수\n2\n'})]).stdin, '민수\n2\n');
});
test('stdin only: meaningful whitespace preserved', () => {
  assert.equal(accepted([blank({stdinText:'  Jin  \n2'})]).stdin, '  Jin  \n2');
});
test('stdin only: 0 and blank lines allowed', () => {
  assert.equal(accepted([blank({stdinText:'0\n\n4'})]).stdin, '0\n\n4');
});
test('function only: backwards-compatible payload', () => {
  const x = accepted([blank({functionName:'compute',argsText:'[4]'})]);
  assert.equal(x.stdin, undefined);
  assert.deepEqual(x.functionCases, [{function:'compute',args:[4],kwargs:{}}]);
});
test('both: same shared stdin and case stdin', () => {
  const x = accepted([blank({functionName:'compute',argsText:'[4]',stdinText:'민수\n2'})]);
  assert.equal(x.stdin, '민수\n2');
  assert.equal(x.functionCases[0].stdin, '민수\n2');
});
test('mixed: unnamed stdin first then actual function', () => {
  const x = accepted([blank({stdinText:'민수\n2'}),blank({functionName:'compute',argsText:'[4]'})]);
  assert.equal(x.stdin,'민수\n2');
  assert.deepEqual(x.functionCases,[{function:'compute',args:[4],kwargs:{}}]);
});
test('mixed: named function first then standalone stdin', () => {
  const x = accepted([blank({functionName:'compute',argsText:'[4]'}),blank({stdinText:'민수\n2'})]);
  assert.equal(x.stdin,'민수\n2');
  assert.equal(x.functionCases.length,1);
});
test('two functions with different stdin keep overrides', () => {
  const x = accepted([blank({functionName:'f',stdinText:'1'}),blank({functionName:'g',stdinText:'2'})]);
  assert.equal(x.stdin,'1');
  assert.deepEqual(x.functionCases.map(c=>c.stdin),['1','2']);
});
test('additional untouched blank row is ignored', () => {
  const x = accepted([blank({stdinText:'A'}),blank()]);
  assert.equal(x.stdin,'A'); assert.equal(x.functionCases,undefined);
});
test('empty submission rejected', () => rejected([blank()],'사용자 입력값'));
test('nameless non-default arguments rejected', () => rejected([blank({stdinText:'2',argsText:'[4]'})],'함수 이름'));
test('nameless non-default kwargs rejected', () => rejected([blank({stdinText:'2',kwargsText:'{"x":1}'})],'함수 이름'));
test('invalid JSON args rejected for named function', () => rejected([blank({functionName:'f',argsText:'[abc]'})],'순서대로'));
test('non-array args rejected', () => rejected([blank({functionName:'f',argsText:'4'})],'대괄호'));
test('invalid JSON kwargs rejected', () => rejected([blank({functionName:'f',kwargsText:'{x:1}'})],'이름을 지정'));
test('non-object kwargs rejected', () => rejected([blank({functionName:'f',kwargsText:'[]'})],'중괄호'));
test('more than 8192 stdin chars rejected', () => rejected([blank({stdinText:'a'.repeat(8193)})],'제한'));
test('more than 128 newlines rejected', () => rejected([blank({stdinText:'x\n'.repeat(129)})],'제한'));
test('exactly 128 newlines accepted', () => {
  const str = 'x\n'.repeat(128);
  assert.equal(accepted([blank({stdinText:str})]).stdin,str);
});
