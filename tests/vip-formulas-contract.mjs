import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const formulasSection = html.slice(html.indexOf('const VIP_FORMULAS = ['), html.indexOf('// MARKETS -'));

const addedNames = [
  'ดับเบิ้ลบวก', 'บวกคงที่', 'มังกรทอง', 'เศรษฐีพันล้าน',
  'พิกัด บน (สูตรยอดนิยม)', 'พิกัด ล่าง (สูตรผลรวม 3 ตัวบน)', 'มหาโชค (บน)', 'นางพญา (ล่าง)',
  'ปักสิบ บน (สูตรบวกคงที่ 3)', 'ปักสิบ บน เดินหน้า', 'ปักสิบ บน กระต่ายน้อย',
  'ปักสิบ ล่าง บวกคงที่ 3', 'ปักสิบ ล่าง (สูตรคูณดรรชนี)', 'ปักสิบ ล่าง น้องหมีขาว',
  'ปักหน่วย บน (สูตรบวกคงที่ 2)', 'ปักหน่วย บน พญาวานร',
  'ปักหน่วย ล่าง คูณ 9', 'ปักหน่วย ล่าง (สูตรสิงโตทองคำ)',
];

for (const name of addedNames) {
  assert.match(formulasSection, new RegExp(name.replace(/[()]/g, '\\$&')), `missing formula: ${name}`);
}

assert.match(html, /const multiFormula\s*=|valuesFn/,
  'formula engine supports formulas with non-consecutive outputs');
assert.match(html, /T10|t\[1\]\s*\*\s*10/,
  'two-digit upper value is supported');
assert.match(html, /TB10|b\[0\]\s*\*\s*10/,
  'two-digit lower value is supported');
assert.match(html, /สูตร VIP ที่แสดง 8 สูตร|ทั้งหมด \(8\)/,
  'UI shows the 8 active formulas');
assert.match(html, /สูตรทั้งหมด 18 สูตร|รวม 18 สูตร/,
  'UI keeps the 18-formula system total');
assert.doesNotMatch(html, /39 สูตร|ทั้งหมด \(39\)|21 สูตร|ทั้งหมด \(21\)/,
  'UI has no stale formula-count text');

const engineSource = html.slice(html.indexOf('const digit ='), html.indexOf('// MARKETS -'));
const formulas = new Function(`${engineSource}; return VIP_FORMULAS;`)();
const displayFormulaIds = new Function(`${engineSource}; return [...DISPLAY_FORMULA_IDS];`)();
assert.deepEqual(displayFormulaIds, [23, 24, 26, 27, 30, 34, 36, 39],
  'display uses the 8 active reference formulas');
const digit = value => ((Number(value) % 10) + 10) % 10;
const calculate = (formula) => {
  const top = ['1', '5', '8'];
  const bottom = ['2', '3'];
  if (typeof formula.valuesFn === 'function') {
    return formula.valuesFn(top, bottom).map(digit);
  }
  const base = formula.digitFn(top, bottom);
  return Array.from({ length: formula.ballCount }, (_, index) =>
    digit(base + formula.startOffset + index));
};
const values = name => calculate(formulas.find(formula => formula.name === name));

assert.deepEqual(values('ดับเบิ้ลบวก'), [3, 2]);
assert.deepEqual(values('รูดบนล่าง (สูตรบวกคงที่)'), [6, 8]);
assert.deepEqual(values('รูดบนล่าง (สูตรมังกรทอง)'), [2, 3]);
assert.deepEqual(values('เศรษฐีพันล้าน'), [6, 3]);
assert.deepEqual(values('พิกัด บน (สูตรยอดนิยม)'), [8, 9, 0]);
assert.deepEqual(values('พิกัด ล่าง (สูตรผลรวม 3 ตัวบน)'), [4, 5, 6]);
assert.deepEqual(values('มหาโชค (บน)'), [8]);
assert.deepEqual(values('นางพญา (ล่าง)'), [2]);
assert.deepEqual(values('ปักสิบ บน (สูตรบวกคงที่ 3)'), [3, 4, 5, 6, 7, 8]);
assert.deepEqual(values('ปักสิบ ล่าง (สูตรคูณดรรชนี)'), [6, 7, 8, 9, 0, 1]);
assert.deepEqual(values('ปักหน่วย บน (สูตรบวกคงที่ 2)'), [6, 7, 8, 9, 0, 1]);
assert.deepEqual(values('ปักหน่วย ล่าง คูณ 9'), [7]);
assert.deepEqual(values('ปักหน่วย ล่าง (สูตรสิงโตทองคำ)'), [0, 1, 2, 3, 4, 5]);

console.log('VIP formula additions contract: PASS');
