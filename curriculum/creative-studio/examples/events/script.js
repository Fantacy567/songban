// Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
// 按钮的名字由 HTML 决定；点击后的行为由这里的事件处理函数决定。
document.querySelector('#hello').addEventListener('click', () => {
  document.querySelector('#result').textContent = '你好，这是我想说的话！';
});
document.querySelector('#reset').addEventListener('click', () => {
  document.querySelector('#result').textContent = '';
});
