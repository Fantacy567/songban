// Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
let count = 0;
const step = 1;
const output = document.querySelector('#count');
output.textContent = String(count);
document.querySelector('#add').addEventListener('click', () => {
  count = count + step;
  // 变量改变后，还要把新值放到页面上。
  output.textContent = String(count);
});
