// Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
let count = 0;
const target = 3;
function show() {
  document.querySelector('#count').textContent = String(count);
  if (count >= target) {
    document.querySelector('#result').textContent = '达到目标了';
  } else {
    document.querySelector('#result').textContent = '还没达到目标';
  }
}
document.querySelector('#add').addEventListener('click', () => {
  count = count + 1;
  show();
});
show();
