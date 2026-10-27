#!/bin/bash
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "请先在本目录创建虚拟环境并安装依赖（见 README）。"
  read -r -p "按回车关闭…"
  exit 1
fi
.venv/bin/python scripts/apply_aliyun_access_key.py
echo
read -r -p "按回车关闭…"
