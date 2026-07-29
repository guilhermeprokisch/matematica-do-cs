// Executa o <script> do livro num DOM mínimo: qualquer exceção = lab quebrado.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2] || 'docs/index.html', 'utf8');

const inputs = {};
const radioChecked = {};
const inputRe = /<input([^>]*)>/g;
let m;
while ((m = inputRe.exec(src))) {
  const attrs = m[1];
  const id = (attrs.match(/id="([^"]+)"/) || [])[1];
  const name = (attrs.match(/name="([^"]+)"/) || [])[1];
  const value = (attrs.match(/value="([^"]+)"/) || [])[1];
  const checked = /\schecked/.test(attrs);
  if (id) inputs[id] = { value: value || '', checked };
  if (name && checked) radioChecked[name] = { value: value || '', checked: true, addEventListener() {} };
}

function El(tag) {
  this.tagName = tag; this.children = []; this.attrs = {}; this.style = {};
  this.className = ''; this.value = ''; this.checked = false; this._text = '';
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
El.prototype.addEventListener = function () {};
Object.defineProperty(El.prototype, 'textContent', {
  get() { return this._text; },
  set(v) { this._text = String(v); this.children = []; },
});

const REG = {};
function getEl(id) {
  if (!REG[id]) {
    const e = new El('div');
    if (inputs[id]) { e.value = inputs[id].value; e.checked = inputs[id].checked; }
    REG[id] = e;
  }
  return REG[id];
}

global.document = {
  createElement: (t) => new El(t),
  createElementNS: (ns, t) => new El(t),
  createTextNode: (t) => ({ text: t }),
  getElementById: getEl,
  querySelector: (sel) => {
    const mm = sel.match(/input\[name=([^\]]+)\]:checked/);
    if (mm) return radioChecked[mm[1]] || null;
    return new El('div');
  },
  querySelectorAll: () => [],
};
global.getComputedStyle = () => ({ getPropertyValue: () => '#888' });
global.window = global;

const scriptSrc = src.match(/<script>([\s\S]*?)<\/script>/)[1];
try {
  eval(scriptSrc);
  console.log('TODOS OS LABS INICIALIZARAM SEM EXCEÇÃO');
  const checks = {
    'l11-read (economia)': getEl('l11-read').children.length,
    'l12-read (erro de mira)': getEl('l12-read').children.length,
    'l13-read (tagging)': getEl('l13-read').children.length,
    'l14-read (peeker)': getEl('l14-read').children.length,
    'l7-read (ttk)': getEl('l7-read').children.length,
  };
  for (const k in checks) console.log(' ', k, '→', checks[k], 'cards');
} catch (e) {
  console.log('EXCEÇÃO:', e.message);
  console.log(e.stack.split('\n').slice(0, 4).join('\n'));
  process.exit(1);
}
